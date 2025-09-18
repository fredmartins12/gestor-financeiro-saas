import sqlite3
import json
import csv
import io
from datetime import datetime, timedelta
from flask import Flask, jsonify, request, render_template, g, Response, redirect, url_for, flash
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, UserMixin, login_user, logout_user, current_user, login_required

# --- Configuração Inicial ---
app = Flask(__name__)
# IMPORTANTE: Mude esta chave para algo único e secreto em um ambiente de produção!
app.config['SECRET_KEY'] = 'uma-chave-secreta-muito-dificil-de-adivinhar' 
DATABASE = 'gestao_apostas.db'

# --- Configuração do Flask-Login ---
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login' # Redireciona usuários não logados para a rota de login

# --- Conexão com o Banco de Dados ---
def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

# --- Modelo de Usuário para o Flask-Login ---
class User(UserMixin):
    def __init__(self, id, email):
        self.id = id
        self.email = email

@login_manager.user_loader
def load_user(user_id):
    db = get_db()
    user_row = db.execute("SELECT * FROM usuarios WHERE id = ?", (user_id,)).fetchone()
    if user_row:
        return User(id=user_row['id'], email=user_row['email'])
    return None

# --- Rotas de Autenticação ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        db = get_db()
        user_row = db.execute("SELECT * FROM usuarios WHERE email = ?", (email,)).fetchone()
        
        if user_row and check_password_hash(user_row['senha_hash'], password):
            user = User(id=user_row['id'], email=user_row['email'])
            login_user(user)
            return redirect(url_for('index'))
        else:
            flash('Email ou senha inválidos.', 'error')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        db = get_db()
        user_row = db.execute("SELECT id FROM usuarios WHERE email = ?", (email,)).fetchone()

        if user_row:
            flash('Este email já está cadastrado.', 'error')
            return redirect(url_for('register'))
        
        if len(password) < 8:
            flash('A senha deve ter no mínimo 8 caracteres.', 'error')
            return redirect(url_for('register'))

        password_hash = generate_password_hash(password, method='pbkdf2:sha256')
        db.execute("INSERT INTO usuarios (email, senha_hash) VALUES (?, ?)", (email, password_hash))
        db.commit()
        flash('Conta criada com sucesso! Faça o login.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# --- Rota Principal da Aplicação ---
@app.route('/')
@login_required
def index():
    return render_template('index.html')

# --- Função de Autenticação para a API ---
def get_current_user_id():
    return current_user.id

# --- API Endpoints (Protegidos) ---

@app.route('/api/dados-iniciais', methods=['GET'])
@login_required
def get_dados_iniciais():
    user_id = get_current_user_id()
    db = get_db()
    contas = [dict(row) for row in db.execute("SELECT * FROM contas WHERE user_id = ? AND ativa = 1 ORDER BY nome", (user_id,)).fetchall()]
    operacoes_ativas = [dict(row) for row in db.execute("SELECT t.*, c.nome as nome_conta FROM transacoes t JOIN contas c ON t.conta_id = c.id WHERE t.user_id = ? AND t.tipo = 'bet_placed' AND json_extract(t.detalhes, '$.status') = 'ativa'", (user_id,)).fetchall()]
    historico = [dict(row) for row in db.execute("SELECT t.*, c.nome as nome_conta FROM transacoes t JOIN contas c ON t.conta_id = c.id WHERE t.user_id = ? ORDER BY t.data_criacao DESC LIMIT 30", (user_id,)).fetchall()]
    now = datetime.now()
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    resumo_mes_transacoes = dict(db.execute("SELECT SUM(CASE WHEN valor > 0 THEN valor ELSE 0 END) as entradas, SUM(CASE WHEN valor < 0 THEN valor ELSE 0 END) as saidas FROM transacoes WHERE user_id = ? AND data_criacao >= ? AND tipo NOT IN ('bet_placed', 'bet_won')", (user_id, start_of_month)).fetchone())
    lucro_prejuizo_mes = db.execute("SELECT SUM(valor) as lucro_prejuizo FROM transacoes WHERE user_id = ? AND data_criacao >= ? AND tipo IN ('bet_placed', 'bet_won')", (user_id, start_of_month)).fetchone()['lucro_prejuizo'] or 0
    return jsonify({
        'contas': contas, 'operacoesAtivas': operacoes_ativas, 'historico': historico,
        'resumoFinanceiro': { 'monthly_credits': resumo_mes_transacoes['entradas'] or 0, 'monthly_debits': resumo_mes_transacoes['saidas'] or 0, 'monthly_net': lucro_prejuizo_mes }
    })

@app.route('/api/contas', methods=['POST'])
@login_required
def add_conta():
    user_id, data = get_current_user_id(), request.get_json()
    db = get_db()
    db.execute("INSERT INTO contas (user_id, nome, casa_de_aposta, saldo, saldo_freebets, meta, volume_clube, dia_pagamento, valor_pagamento, observacoes, data_ultimo_codigo) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (user_id, data.get('nome'), data.get('casaDeAposta'), data.get('saldo', 0), data.get('saldoFreebets', 0), data.get('meta', 100), data.get('volumeClube', 0), data.get('diaPagamento'), data.get('valorPagamento'), data.get('observacoes'), data.get('dataUltimoCodigo')))
    db.commit()
    return jsonify({'message': 'Conta criada com sucesso'}), 201

@app.route('/api/contas/<int:conta_id>', methods=['PUT'])
@login_required
def update_conta(conta_id):
    user_id, data = get_current_user_id(), request.get_json()
    db = get_db()
    cursor = db.execute("UPDATE contas SET nome=?, casa_de_aposta=?, saldo=?, saldo_freebets=?, meta=?, volume_clube=?, dia_pagamento=?, valor_pagamento=?, observacoes=?, ultimo_periodo_pago=?, data_ultimo_codigo=? WHERE id = ? AND user_id = ?",
        (data.get('nome'), data.get('casaDeAposta'), data.get('saldo'), data.get('saldoFreebets'), data.get('meta'), data.get('volumeClube'), data.get('diaPagamento'), data.get('valorPagamento'), data.get('observacoes'), data.get('ultimoPeriodoPago'), data.get('dataUltimoCodigo'), conta_id, user_id))
    db.commit()
    return jsonify({'message': 'Conta atualizada com sucesso'}) if cursor.rowcount > 0 else (jsonify({'error': 'Conta não encontrada'}), 404)

@app.route('/api/contas/<int:conta_id>', methods=['DELETE'])
@login_required
def deactivate_conta(conta_id):
    user_id = get_current_user_id()
    db = get_db()
    cursor = db.execute("UPDATE contas SET ativa = 0 WHERE id = ? AND user_id = ?", (conta_id, user_id))
    db.commit()
    return jsonify({'message': 'Conta desativada com sucesso'}) if cursor.rowcount > 0 else (jsonify({'error': 'Conta não encontrada'}), 404)

@app.route('/api/operacoes', methods=['POST'])
@login_required
def registrar_operacao():
    user_id, op_data = get_current_user_id(), request.get_json()
    db = get_db()
    try:
        with db:
            operation_id = f"op_{int(datetime.now().timestamp())}"
            for leg in op_data.get('legs', []):
                for bet in leg.get('accounts', []):
                    conta_id, stake, is_freebet, odd = int(bet.get('accountId')), float(bet.get('stake')), bet.get('isFreebet', False), float(leg.get('odd'))
                    if is_freebet: db.execute("UPDATE contas SET saldo_freebets = saldo_freebets - ? WHERE id = ?", (stake, conta_id))
                    else: db.execute("UPDATE contas SET saldo = saldo - ? WHERE id = ?", (stake, conta_id))
                    detalhes = {'operationId': operation_id, 'result': leg.get('result'), 'category': op_data.get('category'),'odd': odd, 'stake': stake, 'isFreebet': is_freebet, 'status': 'ativa'}
                    db.execute("INSERT INTO transacoes (conta_id, user_id, tipo, valor, descricao, detalhes) VALUES (?, ?, ?, ?, ?, ?)", (conta_id, user_id, 'bet_placed', -stake if not is_freebet else 0, f"{op_data.get('gameName')} - {leg.get('result')}", json.dumps(detalhes)))
        return jsonify({'message': 'Operação registrada com sucesso!'})
    except Exception as e: return jsonify({'error': str(e)}), 500

@app.route('/api/operacoes/resolver', methods=['POST'])
@login_required
def resolver_operacao():
    user_id, data = get_current_user_id(), request.get_json()
    operation_id, winning_market = data.get('operationId'), data.get('winningMarket')
    db = get_db()
    try:
        with db:
            apostas = [dict(row) for row in db.execute("SELECT * FROM transacoes WHERE user_id = ? AND tipo = 'bet_placed' AND json_extract(detalhes, '$.operationId') = ? AND json_extract(detalhes, '$.status') = 'ativa'", (user_id, operation_id)).fetchall()]
            if not apostas: return jsonify({'error': 'Operação não encontrada ou já resolvida'}), 404

            if winning_market is None:
                for aposta in apostas:
                    detalhes = json.loads(aposta['detalhes'])
                    detalhes['status'] = 'perdida'
                    db.execute("UPDATE transacoes SET detalhes = ? WHERE id = ?", (json.dumps(detalhes), aposta['id']))
                return jsonify({'message': 'Operação marcada como perdida!'})

            for aposta in apostas:
                detalhes = json.loads(aposta['detalhes'])
                is_winner = detalhes.get('result') == winning_market
                if is_winner:
                    retorno = detalhes['stake'] * detalhes['odd']
                    if detalhes['isFreebet']: retorno -= detalhes['stake']
                    db.execute("UPDATE contas SET saldo = saldo + ? WHERE id = ?", (retorno, aposta['conta_id']))
                    db.execute("INSERT INTO transacoes (conta_id, user_id, tipo, valor, descricao, detalhes) VALUES (?, ?, ?, ?, ?, ?)", (aposta['conta_id'], user_id, 'bet_won', retorno, f"Ganho: {aposta['descricao']}", json.dumps(detalhes)))
                    detalhes['status'] = 'ganha'
                else:
                    detalhes['status'] = 'perdida'
                db.execute("UPDATE transacoes SET detalhes = ? WHERE id = ?", (json.dumps(detalhes), aposta['id']))
        return jsonify({'message': 'Operação resolvida com sucesso!'})
    except Exception as e: return jsonify({'error': str(e)}), 500

@app.route('/api/transacoes/generico', methods=['POST'])
@login_required
def add_transacao_generica():
    user_id, data = get_current_user_id(), request.get_json()
    conta_id, tipo, valor, descricao = data.get('accountId'), data.get('type'), float(data.get('amount')), data.get('description')
    valor_real = valor if tipo in ['deposit', 'bonus', 'other_credit'] else -valor
    db = get_db()
    try:
        with db:
            if db.execute("UPDATE contas SET saldo = saldo + ? WHERE id = ? AND user_id = ?", (valor_real, conta_id, user_id)).rowcount == 0: return jsonify({'error': 'Conta não encontrada'}), 404
            db.execute("INSERT INTO transacoes (conta_id, user_id, tipo, valor, descricao) VALUES (?, ?, ?, ?, ?)", (conta_id, user_id, tipo, valor_real, descricao))
        return jsonify({'message': 'Transação registrada com sucesso!'})
    except Exception as e: return jsonify({'error': str(e)}), 500

@app.route('/api/transferencia', methods=['POST'])
@login_required
def transferencia_entre_contas():
    user_id, data = get_current_user_id(), request.get_json()
    from_id, to_id, valor, descricao = data.get('fromId'), data.get('toId'), float(data.get('amount')), data.get('description')
    db = get_db()
    try:
        with db:
            if db.execute("UPDATE contas SET saldo = saldo - ? WHERE id = ? AND user_id = ?", (valor, from_id, user_id)).rowcount == 0: return jsonify({'error': 'Conta de origem não encontrada'}), 404
            if db.execute("UPDATE contas SET saldo = saldo + ? WHERE id = ? AND user_id = ?", (valor, to_id, user_id)).rowcount == 0: return jsonify({'error': 'Conta de destino não encontrada'}), 404
            from_name = db.execute("SELECT nome FROM contas WHERE id = ?", (from_id,)).fetchone()['nome']
            to_name = db.execute("SELECT nome FROM contas WHERE id = ?", (to_id,)).fetchone()['nome']
            db.execute("INSERT INTO transacoes (conta_id, user_id, tipo, valor, descricao) VALUES (?, ?, ?, ?, ?)", (from_id, user_id, 'transfer_out', -valor, f"Para: {to_name} ({descricao})"))
            db.execute("INSERT INTO transacoes (conta_id, user_id, tipo, valor, descricao) VALUES (?, ?, ?, ?, ?)", (to_id, user_id, 'transfer_in', valor, f"De: {from_name} ({descricao})"))
        return jsonify({'message': 'Transferência realizada com sucesso!'})
    except Exception as e: return jsonify({'error': str(e)}), 500

@app.route('/api/transacoes/<int:transacao_id>', methods=['DELETE'])
@login_required
def reverter_transacao(transacao_id):
    user_id = get_current_user_id()
    db = get_db()
    try:
        with db:
            transacao = db.execute("SELECT * FROM transacoes WHERE id = ? AND user_id = ?", (transacao_id, user_id)).fetchone()
            if not transacao: return jsonify({'error': 'Transação não encontrada'}), 404
            transacao = dict(transacao)
            detalhes = json.loads(transacao['detalhes']) if transacao['detalhes'] else {}
            operation_id = detalhes.get('operationId')
            if operation_id:
                apostas_relacionadas = [dict(row) for row in db.execute("SELECT * FROM transacoes WHERE user_id = ? AND json_extract(detalhes, '$.operationId') = ?", (user_id, operation_id)).fetchall()]
                for aposta in apostas_relacionadas:
                    db.execute("UPDATE contas SET saldo = saldo - ? WHERE id = ?", (aposta['valor'], aposta['conta_id']))
                    aposta_detalhes = json.loads(aposta['detalhes']) if aposta['detalhes'] else {}
                    if aposta['tipo'] == 'bet_placed' and aposta_detalhes.get('isFreebet'):
                        db.execute("UPDATE contas SET saldo_freebets = saldo_freebets + ? WHERE id = ?", (aposta_detalhes.get('stake', 0), aposta['conta_id']))
                    db.execute("DELETE FROM transacoes WHERE id = ?", (aposta['id'],))
            else:
                db.execute("UPDATE contas SET saldo = saldo - ? WHERE id = ?", (transacao['valor'], transacao['conta_id']))
                db.execute("DELETE FROM transacoes WHERE id = ?", (transacao_id,))
        return jsonify({'message': 'Transação e seus efeitos foram revertidos!'})
    except Exception as e: return jsonify({'error': str(e)}), 500

@app.route('/api/backup', methods=['GET'])
@login_required
def backup_dados():
    user_id = get_current_user_id()
    db = get_db()
    contas = [dict(row) for row in db.execute("SELECT * FROM contas WHERE user_id = ?", (user_id,)).fetchall()]
    transacoes = [dict(row) for row in db.execute("SELECT * FROM transacoes WHERE user_id = ?", (user_id,)).fetchall()]
    backup_data = {'backupDate': datetime.now().isoformat(), 'contas': contas, 'transacoes': transacoes}
    return Response(json.dumps(backup_data, indent=2), mimetype='application/json', headers={'Content-Disposition': 'attachment;filename=backup_gestao.json'})

@app.route('/api/relatorio', methods=['GET'])
@login_required
def get_relatorio():
    user_id = get_current_user_id()
    year = request.args.get('year', default=datetime.now().year, type=int)
    month = request.args.get('month', default=datetime.now().month, type=int)
    start_date, end_date = datetime(year, month, 1), (datetime(year, month, 1) + timedelta(days=32)).replace(day=1)
    db = get_db()
    
    transacoes = [dict(row) for row in db.execute("SELECT t.*, c.nome as nome_conta, c.casa_de_aposta FROM transacoes t JOIN contas c ON t.conta_id = c.id WHERE t.user_id = ? AND t.data_criacao >= ? AND t.data_criacao < ?", (user_id, start_date, end_date)).fetchall()]
    
    net_profit = sum(t['valor'] for t in transacoes if t['tipo'] in ['bet_placed', 'bet_won'])
    total_expenses = sum(t['valor'] for t in transacoes if t['tipo'] == 'expense')
    total_payments = sum(t['valor'] for t in transacoes if t['tipo'] == 'payment')

    analysis = {}
    for t in transacoes:
        if t['casa_de_aposta'] != 'pessoal':
            if t['conta_id'] not in analysis: 
                analysis[t['conta_id']] = {'name': t['nome_conta'], 'profit': 0, 'wagered': 0, 'betCount': 0}
            if t['tipo'] in ['bet_placed', 'bet_won']: 
                analysis[t['conta_id']]['profit'] += t['valor']
            if t['tipo'] == 'bet_placed':
                details = json.loads(t['detalhes']) if t['detalhes'] else {}
                analysis[t['conta_id']]['wagered'] += details.get('stake', 0)
                analysis[t['conta_id']]['betCount'] += 1
                
    report_data = {
        'summary': {
            'netProfit': net_profit, 
            'totalExpenses': total_expenses, 
            'totalPayments': total_payments 
        },
        'accountAnalysis': list(analysis.values()),
        'expenses': [t for t in transacoes if t['tipo'] == 'expense']
    }
    return jsonify(report_data)

@app.route('/api/contas/<int:conta_id>/pagar', methods=['POST'])
@login_required
def registrar_pagamento(conta_id):
    user_id = get_current_user_id()
    db = get_db()
    try:
        periodo_pago = datetime.now().strftime('%Y-%m')
        cursor = db.execute("UPDATE contas SET ultimo_periodo_pago = ? WHERE id = ? AND user_id = ?",
                            (periodo_pago, conta_id, user_id))
        db.commit()
        if cursor.rowcount > 0:
            return jsonify({'message': 'Pagamento registrado com sucesso!'})
        else:
            return jsonify({'error': 'Conta não encontrada'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/restore', methods=['POST'])
@login_required
def restore_backup():
    user_id = get_current_user_id()
    if 'backupFile' not in request.files:
        return jsonify({'error': 'Nenhum arquivo enviado'}), 400
    file = request.files['backupFile']
    if file.filename == '':
        return jsonify({'error': 'Nenhum arquivo selecionado'}), 400
    try:
        backup_data = json.load(file)
        contas = backup_data.get('contas', [])
        transacoes = backup_data.get('transacoes', [])
        db = get_db()
        with db:
            db.execute("DELETE FROM transacoes WHERE user_id = ?", (user_id,))
            db.execute("DELETE FROM contas WHERE user_id = ?", (user_id,))
            for conta in contas:
                db.execute("""
                    INSERT INTO contas (id, user_id, nome, casa_de_aposta, saldo, saldo_freebets, meta, volume_clube, dia_pagamento, valor_pagamento, observacoes, ultimo_periodo_pago, ativa, data_ultimo_codigo)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (conta.get('id'), user_id, conta.get('nome'), conta.get('casa_de_aposta'), conta.get('saldo'), conta.get('saldo_freebets'), conta.get('meta'), conta.get('volume_clube'), conta.get('dia_pagamento'), conta.get('valor_pagamento'), conta.get('observacoes'), conta.get('ultimo_periodo_pago'), conta.get('ativa'), conta.get('data_ultimo_codigo')))
            for transacao in transacoes:
                 db.execute("""
                    INSERT INTO transacoes (id, conta_id, user_id, tipo, valor, descricao, detalhes, data_criacao)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (transacao.get('id'), transacao.get('conta_id'), user_id, transacao.get('tipo'), transacao.get('valor'), transacao.get('descricao'), transacao.get('detalhes'), transacao.get('data_criacao')))
        return jsonify({'message': f'{len(contas)} contas e {len(transacoes)} transações restauradas com sucesso!'})
    except Exception as e:
        return jsonify({'error': f'Erro ao processar o backup: {str(e)}'}), 500

@app.route('/api/import-csv', methods=['POST'])
@login_required
def import_csv():
    user_id = get_current_user_id()
    if 'csvFile' not in request.files:
        return jsonify({'error': 'Nenhum arquivo CSV enviado'}), 400
    file = request.files['csvFile']
    if file.filename == '':
        return jsonify({'error': 'Nenhum arquivo selecionado'}), 400
    try:
        stream = io.StringIO(file.stream.read().decode("UTF-8"), newline=None)
        csv_reader = csv.DictReader(stream)
        contas_para_processar = list(csv_reader)
        criadas = 0
        atualizadas = 0
        db = get_db()
        with db:
            for conta_data in contas_para_processar:
                nome = conta_data.get('nome')
                if not nome: continue
                conta_existente = db.execute("SELECT id FROM contas WHERE nome = ? AND user_id = ?", (nome, user_id)).fetchone()
                dados = {
                    "nome": nome, "casa_de_aposta": conta_data.get('casa_de_aposta') or None, "saldo": float(conta_data.get('saldo') or 0), "saldo_freebets": float(conta_data.get('saldo_freebets') or 0), "dia_pagamento": int(conta_data.get('dia_pagamento')) if conta_data.get('dia_pagamento') else None, "valor_pagamento": float(conta_data.get('valor_pagamento')) if conta_data.get('valor_pagamento') else None, "observacoes": conta_data.get('observacoes') or None, "data_ultimo_codigo": conta_data.get('data_ultimo_codigo') or None,
                }
                if conta_existente:
                    db.execute("""
                        UPDATE contas SET casa_de_aposta=?, saldo=?, saldo_freebets=?, dia_pagamento=?, valor_pagamento=?, observacoes=?, data_ultimo_codigo=?
                        WHERE id = ? AND user_id = ?
                    """, (dados['casa_de_aposta'], dados['saldo'], dados['saldo_freebets'], dados['dia_pagamento'], dados['valor_pagamento'], dados['observacoes'], dados['data_ultimo_codigo'], conta_existente['id'], user_id))
                    atualizadas += 1
                else:
                    db.execute("""
                        INSERT INTO contas (user_id, nome, casa_de_aposta, saldo, saldo_freebets, dia_pagamento, valor_pagamento, observacoes, data_ultimo_codigo)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (user_id, dados['nome'], dados['casa_de_aposta'], dados['saldo'], dados['saldo_freebets'], dados['dia_pagamento'], dados['valor_pagamento'], dados['observacoes'], dados['data_ultimo_codigo']))
                    criadas += 1
        return jsonify({'message': f'{criadas} contas criadas e {atualizadas} atualizadas com sucesso!'})
    except Exception as e:
        return jsonify({'error': f'Erro ao processar o CSV: {str(e)}'}), 500
        
@app.route('/api/csv-template', methods=['GET'])
@login_required
def csv_template():
    header = "nome,casa_de_aposta,saldo,saldo_freebets,dia_pagamento,valor_pagamento,observacoes,data_ultimo_codigo"
    return Response(
        header,
        mimetype="text/csv",
        headers={"Content-disposition": "attachment; filename=modelo_contas.csv"}
    )

if __name__ == '__main__':
    app.run(debug=True)