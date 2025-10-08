import os
import psycopg2
import psycopg2.extras  # Essencial para retornar linhas como dicionários
import json
import csv
import io
from datetime import datetime, timedelta
from flask import Flask, jsonify, request, render_template, g, Response, redirect, url_for, flash
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, UserMixin, login_user, logout_user, current_user, login_required

# --- Configuração Inicial ---
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', '564312')
DATABASE_URL = os.environ.get('DATABASE_URL')  # URL do PostgreSQL no ambiente

# --- Configuração do Flask-Login ---
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# --- Conexão com o Banco de Dados ---
def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = psycopg2.connect(DATABASE_URL)
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

# --- Modelo de Usuário ---
class User(UserMixin):
    def __init__(self, id, email):
        self.id = id
        self.email = email

@login_manager.user_loader
def load_user(user_id):
    with get_db().cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
        cursor.execute("SELECT * FROM usuarios WHERE id = %s", (user_id,))
        user_row = cursor.fetchone()
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
        with get_db().cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
            cursor.execute("SELECT * FROM usuarios WHERE email = %s", (email,))
            user_row = cursor.fetchone()
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
        with db.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
            cursor.execute("SELECT id FROM usuarios WHERE email = %s", (email,))
            user_row = cursor.fetchone()
            if user_row:
                flash('Este email já está cadastrado.', 'error')
                return redirect(url_for('register'))
            if len(password) < 8:
                flash('A senha deve ter no mínimo 8 caracteres.', 'error')
                return redirect(url_for('register'))
            password_hash = generate_password_hash(password, method='pbkdf2:sha256')
            cursor.execute("INSERT INTO usuarios (email, senha_hash) VALUES (%s, %s)", (email, password_hash))
        db.commit()
        flash('Conta criada com sucesso! Faça o login.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# --- Rota Principal ---
@app.route('/')
@login_required
def index():
    return render_template('index.html')

# --- Função de Usuário Atual ---
def get_current_user_id():
    return current_user.id

# --- API Endpoints ---
@app.route('/api/dados-iniciais', methods=['GET'])
@login_required
def get_dados_iniciais():
    user_id = get_current_user_id()
    db = get_db()
    with db.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
        cursor.execute("SELECT * FROM contas WHERE user_id = %s AND ativa = TRUE ORDER BY nome", (user_id,))
        contas = cursor.fetchall()
        cursor.execute("SELECT t.*, c.nome as nome_conta FROM transacoes t JOIN contas c ON t.conta_id = c.id WHERE t.user_id = %s AND t.tipo = 'bet_placed' AND t.detalhes->>'status' = 'ativa'", (user_id,))
        operacoes_ativas = cursor.fetchall()
        cursor.execute("SELECT t.*, c.nome as nome_conta FROM transacoes t JOIN contas c ON t.conta_id = c.id WHERE t.user_id = %s ORDER BY t.data_criacao DESC LIMIT 30", (user_id,))
        historico = cursor.fetchall()
        now = datetime.now()
        start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        cursor.execute("SELECT SUM(CASE WHEN valor > 0 THEN valor ELSE 0 END) as entradas, SUM(CASE WHEN valor < 0 THEN valor ELSE 0 END) as saidas FROM transacoes WHERE user_id = %s AND data_criacao >= %s AND tipo NOT IN ('bet_placed', 'bet_won')", (user_id, start_of_month))
        resumo_mes_transacoes = cursor.fetchone()
        cursor.execute("SELECT SUM(valor) as lucro_prejuizo FROM transacoes WHERE user_id = %s AND data_criacao >= %s AND tipo IN ('bet_placed', 'bet_won')", (user_id, start_of_month))
        lucro_prejuizo_mes = cursor.fetchone()['lucro_prejuizo'] or 0
    return jsonify({
        'contas': [dict(row) for row in contas], 
        'operacoesAtivas': [dict(row) for row in operacoes_ativas], 
        'historico': [dict(row) for row in historico],
        'resumoFinanceiro': { 
            'monthly_credits': float(resumo_mes_transacoes['entradas'] or 0), 
            'monthly_debits': float(resumo_mes_transacoes['saidas'] or 0), 
            'monthly_net': float(lucro_prejuizo_mes) 
        }
    })

@app.route('/api/contas', methods=['POST'])
@login_required
def add_conta():
    user_id, data = get_current_user_id(), request.get_json()
    db = get_db()
    with db.cursor() as cursor:
        cursor.execute("INSERT INTO contas (user_id, nome, casa_de_aposta, saldo, saldo_freebets, meta, volume_clube, dia_pagamento, valor_pagamento, observacoes, data_ultimo_codigo) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (user_id, data.get('nome'), data.get('casaDeAposta'), data.get('saldo', 0), data.get('saldoFreebets', 0), data.get('meta', 100), data.get('volumeClube', 0), data.get('diaPagamento'), data.get('valorPagamento'), data.get('observacoes'), data.get('dataUltimoCodigo')))
    db.commit()
    return jsonify({'message': 'Conta criada com sucesso'}), 201

@app.route('/api/contas/<int:conta_id>', methods=['PUT'])
@login_required
def update_conta(conta_id):
    user_id, data = get_current_user_id(), request.get_json()
    db = get_db()
    with db.cursor() as cursor:
        cursor.execute("UPDATE contas SET nome=%s, casa_de_aposta=%s, saldo=%s, saldo_freebets=%s, meta=%s, volume_clube=%s, dia_pagamento=%s, valor_pagamento=%s, observacoes=%s, ultimo_periodo_pago=%s, data_ultimo_codigo=%s WHERE id = %s AND user_id = %s",
            (data.get('nome'), data.get('casaDeAposta'), data.get('saldo'), data.get('saldoFreebets'), data.get('meta'), data.get('volumeClube'), data.get('diaPagamento'), data.get('valorPagamento'), data.get('observacoes'), data.get('ultimoPeriodoPago'), data.get('dataUltimoCodigo'), conta_id, user_id))
        rowcount = cursor.rowcount
    db.commit()
    return jsonify({'message': 'Conta atualizada com sucesso'}) if rowcount > 0 else (jsonify({'error': 'Conta não encontrada'}), 404)

@app.route('/api/contas/<int:conta_id>', methods=['DELETE'])
@login_required
def deactivate_conta(conta_id):
    user_id = get_current_user_id()
    db = get_db()
    with db.cursor() as cursor:
        cursor.execute("UPDATE contas SET ativa = FALSE WHERE id = %s AND user_id = %s", (conta_id, user_id))
        rowcount = cursor.rowcount
    db.commit()
    return jsonify({'message': 'Conta desativada com sucesso'}) if rowcount > 0 else (jsonify({'error': 'Conta não encontrada'}), 404)

@app.route('/api/transacoes', methods=['GET'])
@login_required
def listar_transacoes():
    user_id = get_current_user_id()
    db = get_db()
    with db.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
        cursor.execute("SELECT t.*, c.nome AS nome_conta FROM transacoes t JOIN contas c ON t.conta_id = c.id WHERE t.user_id = %s ORDER BY t.data_criacao DESC", (user_id,))
        transacoes = [dict(row) for row in cursor.fetchall()]
    return jsonify(transacoes)

# Criar transação genérica
@app.route('/api/transacoes', methods=['POST'])
@login_required
def criar_transacao():
    user_id, data = get_current_user_id(), request.get_json()
    conta_id = data.get('accountId')
    tipo = data.get('type')
    valor = float(data.get('amount'))
    descricao = data.get('description')
    valor_real = valor if tipo in ['deposit', 'bonus', 'other_credit'] else -valor
    db = get_db()
    try:
        with db:
            with db.cursor() as cursor:
                cursor.execute("UPDATE contas SET saldo = saldo + %s WHERE id = %s AND user_id = %s", (valor_real, conta_id, user_id))
                if cursor.rowcount == 0:
                    return jsonify({'error': 'Conta não encontrada'}), 404
                cursor.execute("INSERT INTO transacoes (conta_id, user_id, tipo, valor, descricao) VALUES (%s, %s, %s, %s, %s)",
                               (conta_id, user_id, tipo, valor_real, descricao))
        return jsonify({'message': 'Transação registrada com sucesso!'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Editar transação existente
@app.route('/api/transacoes/<int:transacao_id>', methods=['PUT'])
@login_required
def editar_transacao(transacao_id):
    user_id, data = get_current_user_id(), request.get_json()
    db = get_db()
    try:
        with db:
            with db.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                cursor.execute("SELECT * FROM transacoes WHERE id = %s AND user_id = %s", (transacao_id, user_id))
                transacao = cursor.fetchone()
                if not transacao:
                    return jsonify({'error': 'Transação não encontrada'}), 404
                # Reverter valor antigo antes de atualizar
                cursor.execute("UPDATE contas SET saldo = saldo - %s WHERE id = %s", (transacao['valor'], transacao['conta_id']))
                # Atualiza os dados
                novo_valor = float(data.get('amount', transacao['valor']))
                tipo = data.get('type', transacao['tipo'])
                valor_real = novo_valor if tipo in ['deposit', 'bonus', 'other_credit'] else -novo_valor
                descricao = data.get('description', transacao['descricao'])
                cursor.execute("UPDATE transacoes SET tipo = %s, valor = %s, descricao = %s WHERE id = %s",
                               (tipo, valor_real, descricao, transacao_id))
                # Aplicar novo valor no saldo
                cursor.execute("UPDATE contas SET saldo = saldo + %s WHERE id = %s", (valor_real, transacao['conta_id']))
        return jsonify({'message': 'Transação atualizada com sucesso!'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Deletar / reverter transação
@app.route('/api/transacoes/<int:transacao_id>', methods=['DELETE'])
@login_required
def deletar_transacao(transacao_id):
    user_id = get_current_user_id()
    db = get_db()
    try:
        with db:
            with db.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                cursor.execute("SELECT * FROM transacoes WHERE id = %s AND user_id = %s", (transacao_id, user_id))
                transacao = cursor.fetchone()
                if not transacao:
                    return jsonify({'error': 'Transação não encontrada'}), 404

                detalhes = transacao['detalhes'] or {}
                operation_id = detalhes.get('operationId')

                if operation_id:
                    # Reverter todas as apostas relacionadas à operação, somente da conta da transação
                    cursor.execute("SELECT * FROM transacoes WHERE user_id = %s AND detalhes->>'operationId' = %s AND conta_id = %s", (user_id, operation_id, transacao['conta_id']))
                    apostas_relacionadas = cursor.fetchall()
                    for aposta in apostas_relacionadas:
                        aposta_detalhes = aposta['detalhes'] or {}
                        valor = aposta['valor']
                        cursor.execute("UPDATE contas SET saldo = saldo - %s WHERE id = %s", (valor, aposta['conta_id']))
                        if aposta['tipo'] == 'bet_placed' and aposta_detalhes.get('isFreebet'):
                            cursor.execute("UPDATE contas SET saldo_freebets = saldo_freebets + %s WHERE id = %s", (aposta_detalhes.get('stake', 0), aposta['conta_id']))
                        cursor.execute("DELETE FROM transacoes WHERE id = %s", (aposta['id'],))
                else:
                    # Reverter saldo normal
                    cursor.execute("UPDATE contas SET saldo = saldo - %s WHERE id = %s", (transacao['valor'], transacao['conta_id']))
                    cursor.execute("DELETE FROM transacoes WHERE id = %s", (transacao_id,))
        return jsonify({'message': 'Transação revertida com sucesso!'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/operacoes', methods=['POST'])
@login_required
def registrar_operacao():
    user_id, op_data = get_current_user_id(), request.get_json()
    db = get_db()
    try:
        with db:
            with db.cursor() as cursor:
                operation_id = f"op_{int(datetime.now().timestamp())}"
                for leg in op_data.get('legs', []):
                    for bet in leg.get('accounts', []):
                        conta_id, stake, is_freebet, odd = int(bet.get('accountId')), float(bet.get('stake')), bet.get('isFreebet', False), float(leg.get('odd'))
                        if is_freebet:
                            cursor.execute("UPDATE contas SET saldo_freebets = saldo_freebets - %s WHERE id = %s", (stake, conta_id))
                        else:
                            cursor.execute("UPDATE contas SET saldo = saldo - %s WHERE id = %s", (stake, conta_id))
                        detalhes = json.dumps({'operationId': operation_id, 'result': leg.get('result'), 'category': op_data.get('category'),'odd': odd, 'stake': stake, 'isFreebet': is_freebet, 'status': 'ativa'})
                        cursor.execute("INSERT INTO transacoes (conta_id, user_id, tipo, valor, descricao, detalhes) VALUES (%s, %s, %s, %s, %s, %s)", 
                                       (conta_id, user_id, 'bet_placed', -stake if not is_freebet else 0, f"{op_data.get('gameName')} - {leg.get('result')}", detalhes))
        return jsonify({'message': 'Operação registrada com sucesso!'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/operacoes/resolver', methods=['POST'])
@login_required
def resolver_operacao():
    user_id, data = get_current_user_id(), request.get_json()
    operation_id, winning_market = data.get('operationId'), data.get('winningMarket')
    db = get_db()
    try:
        with db: # Gerencia a transação
            with db.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                cursor.execute("SELECT * FROM transacoes WHERE user_id = %s AND tipo = 'bet_placed' AND detalhes->>'operationId' = %s AND detalhes->>'status' = 'ativa'", (user_id, operation_id))
                apostas = cursor.fetchall()
                if not apostas:
                    return jsonify({'error': 'Operação não encontrada ou já resolvida'}), 404

                if winning_market is None:
                    for aposta in apostas:
                        detalhes = dict(aposta['detalhes'])
                        detalhes['status'] = 'perdida'
                        cursor.execute("UPDATE transacoes SET detalhes = %s WHERE id = %s", (json.dumps(detalhes), aposta['id']))
                    return jsonify({'message': 'Operação marcada como perdida!'})

                for aposta in apostas:
                    detalhes = dict(aposta['detalhes'])
                    is_winner = detalhes.get('result') == winning_market
                    if is_winner:
                        retorno = detalhes['stake'] * detalhes['odd']
                        if detalhes['isFreebet']:
                            retorno -= detalhes['stake']
                        cursor.execute("UPDATE contas SET saldo = saldo + %s WHERE id = %s", (retorno, aposta['conta_id']))
                        cursor.execute("INSERT INTO transacoes (conta_id, user_id, tipo, valor, descricao, detalhes) VALUES (%s, %s, %s, %s, %s, %s)", 
                                       (aposta['conta_id'], user_id, 'bet_won', retorno, f"Ganho: {aposta['descricao']}", json.dumps(detalhes)))
                        detalhes['status'] = 'ganha'
                    else:
                        detalhes['status'] = 'perdida'
                    cursor.execute("UPDATE transacoes SET detalhes = %s WHERE id = %s", (json.dumps(detalhes), aposta['id']))
        return jsonify({'message': 'Operação resolvida com sucesso!'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/transacoes/generico', methods=['POST'])
@login_required
def add_transacao_generica():
    user_id, data = get_current_user_id(), request.get_json()
    conta_id, tipo, valor, descricao = data.get('accountId'), data.get('type'), float(data.get('amount')), data.get('description')
    valor_real = valor if tipo in ['deposit', 'bonus', 'other_credit'] else -valor
    db = get_db()
    try:
        with db: # Gerencia a transação
            with db.cursor() as cursor:
                cursor.execute("UPDATE contas SET saldo = saldo + %s WHERE id = %s AND user_id = %s", (valor_real, conta_id, user_id))
                if cursor.rowcount == 0:
                    return jsonify({'error': 'Conta não encontrada'}), 404
                cursor.execute("INSERT INTO transacoes (conta_id, user_id, tipo, valor, descricao) VALUES (%s, %s, %s, %s, %s)", 
                               (conta_id, user_id, tipo, valor_real, descricao))
        return jsonify({'message': 'Transação registrada com sucesso!'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/transferencia', methods=['POST'])
@login_required
def transferencia_entre_contas():
    user_id, data = get_current_user_id(), request.get_json()
    from_id, to_id, valor, descricao = data.get('fromId'), data.get('toId'), float(data.get('amount')), data.get('description')
    db = get_db()
    try:
        with db: # Gerencia a transação
            with db.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                cursor.execute("UPDATE contas SET saldo = saldo - %s WHERE id = %s AND user_id = %s", (valor, from_id, user_id))
                if cursor.rowcount == 0: return jsonify({'error': 'Conta de origem não encontrada'}), 404
                
                cursor.execute("UPDATE contas SET saldo = saldo + %s WHERE id = %s AND user_id = %s", (valor, to_id, user_id))
                if cursor.rowcount == 0: return jsonify({'error': 'Conta de destino não encontrada'}), 404

                cursor.execute("SELECT nome FROM contas WHERE id = %s", (from_id,))
                from_name = cursor.fetchone()['nome']
                
                cursor.execute("SELECT nome FROM contas WHERE id = %s", (to_id,))
                to_name = cursor.fetchone()['nome']
                
                cursor.execute("INSERT INTO transacoes (conta_id, user_id, tipo, valor, descricao) VALUES (%s, %s, %s, %s, %s)", 
                               (from_id, user_id, 'transfer_out', -valor, f"Para: {to_name} ({descricao})"))
                cursor.execute("INSERT INTO transacoes (conta_id, user_id, tipo, valor, descricao) VALUES (%s, %s, %s, %s, %s)", 
                               (to_id, user_id, 'transfer_in', valor, f"De: {from_name} ({descricao})"))
        return jsonify({'message': 'Transferência realizada com sucesso!'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/transacoes/<int:transacao_id>', methods=['DELETE'])
@login_required
def reverter_transacao(transacao_id):
    user_id = get_current_user_id()
    db = get_db()
    try:
        with db: # Gerencia a transação
            with db.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                cursor.execute("SELECT * FROM transacoes WHERE id = %s AND user_id = %s", (transacao_id, user_id))
                transacao = cursor.fetchone()
                if not transacao: return jsonify({'error': 'Transação não encontrada'}), 404

                detalhes = transacao['detalhes'] if transacao['detalhes'] else {}
                operation_id = detalhes.get('operationId')

                if operation_id:
                    cursor.execute("SELECT * FROM transacoes WHERE user_id = %s AND detalhes->>'operationId' = %s", (user_id, operation_id))
                    apostas_relacionadas = cursor.fetchall()
                    for aposta in apostas_relacionadas:
                        cursor.execute("UPDATE contas SET saldo = saldo - %s WHERE id = %s", (aposta['valor'], aposta['conta_id']))
                        aposta_detalhes = aposta['detalhes'] if aposta['detalhes'] else {}
                        if aposta['tipo'] == 'bet_placed' and aposta_detalhes.get('isFreebet'):
                            cursor.execute("UPDATE contas SET saldo_freebets = saldo_freebets + %s WHERE id = %s", (aposta_detalhes.get('stake', 0), aposta['conta_id']))
                        cursor.execute("DELETE FROM transacoes WHERE id = %s", (aposta['id'],))
                else:
                    cursor.execute("UPDATE contas SET saldo = saldo - %s WHERE id = %s", (transacao['valor'], transacao['conta_id']))
                    cursor.execute("DELETE FROM transacoes WHERE id = %s", (transacao_id,))
        return jsonify({'message': 'Transação e seus efeitos foram revertidos!'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/backup', methods=['GET'])
@login_required
def backup_dados():
    user_id = get_current_user_id()
    with get_db().cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
        cursor.execute("SELECT * FROM contas WHERE user_id = %s", (user_id,))
        contas = [dict(row) for row in cursor.fetchall()]
        cursor.execute("SELECT * FROM transacoes WHERE user_id = %s", (user_id,))
        transacoes = [dict(row) for row in cursor.fetchall()]
    backup_data = {'backupDate': datetime.now().isoformat(), 'contas': contas, 'transacoes': transacoes}
    return Response(json.dumps(backup_data, indent=2, default=str), mimetype='application/json', headers={'Content-Disposition': 'attachment;filename=backup_gestao.json'})

@app.route('/api/relatorio', methods=['GET'])
@login_required
def get_relatorio():
    user_id = get_current_user_id()
    year = request.args.get('year', default=datetime.now().year, type=int)
    month = request.args.get('month', default=datetime.now().month, type=int)
    start_date, end_date = datetime(year, month, 1), (datetime(year, month, 1) + timedelta(days=32)).replace(day=1)
    
    with get_db().cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
        cursor.execute("SELECT t.*, c.nome as nome_conta, c.casa_de_aposta FROM transacoes t JOIN contas c ON t.conta_id = c.id WHERE t.user_id = %s AND t.data_criacao >= %s AND t.data_criacao < %s", (user_id, start_date, end_date))
        transacoes = [dict(row) for row in cursor.fetchall()]
    
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
                details = t['detalhes'] if t['detalhes'] else {}
                analysis[t['conta_id']]['wagered'] += details.get('stake', 0)
                analysis[t['conta_id']]['betCount'] += 1
                
    report_data = {
        'summary': {
            'netProfit': float(net_profit), 
            'totalExpenses': float(total_expenses), 
            'totalPayments': float(total_payments) 
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
        with db.cursor() as cursor:
            periodo_pago = datetime.now().strftime('%Y-%m')
            cursor.execute("UPDATE contas SET ultimo_periodo_pago = %s WHERE id = %s AND user_id = %s", (periodo_pago, conta_id, user_id))
            rowcount = cursor.rowcount
        db.commit()
        if rowcount > 0:
            return jsonify({'message': 'Pagamento registrado com sucesso!'})
        else:
            return jsonify({'error': 'Conta não encontrada'}), 404
    except Exception as e:
        db.rollback()
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
        with db: # Gerencia transação
            with db.cursor() as cursor:
                cursor.execute("DELETE FROM transacoes WHERE user_id = %s", (user_id,))
                cursor.execute("DELETE FROM contas WHERE user_id = %s", (user_id,))
                for conta in contas:
                    cursor.execute("""
                        INSERT INTO contas (id, user_id, nome, casa_de_aposta, saldo, saldo_freebets, meta, volume_clube, dia_pagamento, valor_pagamento, observacoes, ultimo_periodo_pago, ativa, data_ultimo_codigo)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (conta.get('id'), user_id, conta.get('nome'), conta.get('casa_de_aposta'), conta.get('saldo'), conta.get('saldo_freebets'), conta.get('meta'), conta.get('volume_clube'), conta.get('dia_pagamento'), conta.get('valor_pagamento'), conta.get('observacoes'), conta.get('ultimo_periodo_pago'), conta.get('ativa'), conta.get('data_ultimo_codigo')))
                for transacao in transacoes:
                     cursor.execute("""
                        INSERT INTO transacoes (id, conta_id, user_id, tipo, valor, descricao, detalhes, data_criacao)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """, (transacao.get('id'), transacao.get('conta_id'), user_id, transacao.get('tipo'), transacao.get('valor'), transacao.get('descricao'), json.dumps(transacao.get('detalhes')), transacao.get('data_criacao')))
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
        with db: # Gerencia transação
            with db.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                for conta_data in contas_para_processar:
                    nome = conta_data.get('nome')
                    if not nome: continue
                    cursor.execute("SELECT id FROM contas WHERE nome = %s AND user_id = %s", (nome, user_id))
                    conta_existente = cursor.fetchone()
                    dados = {
                        "nome": nome, "casa_de_aposta": conta_data.get('casa_de_aposta') or None, "saldo": float(conta_data.get('saldo') or 0), "saldo_freebets": float(conta_data.get('saldo_freebets') or 0), "dia_pagamento": int(conta_data.get('dia_pagamento')) if conta_data.get('dia_pagamento') else None, "valor_pagamento": float(conta_data.get('valor_pagamento')) if conta_data.get('valor_pagamento') else None, "observacoes": conta_data.get('observacoes') or None, "data_ultimo_codigo": conta_data.get('data_ultimo_codigo') or None,
                    }
                    if conta_existente:
                        cursor.execute("""
                            UPDATE contas SET casa_de_aposta=%s, saldo=%s, saldo_freebets=%s, dia_pagamento=%s, valor_pagamento=%s, observacoes=%s, data_ultimo_codigo=%s
                            WHERE id = %s AND user_id = %s
                        """, (dados['casa_de_aposta'], dados['saldo'], dados['saldo_freebets'], dados['dia_pagamento'], dados['valor_pagamento'], dados['observacoes'], dados['data_ultimo_codigo'], conta_existente['id'], user_id))
                        atualizadas += 1
                    else:
                        cursor.execute("""
                            INSERT INTO contas (user_id, nome, casa_de_aposta, saldo, saldo_freebets, dia_pagamento, valor_pagamento, observacoes, data_ultimo_codigo)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
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
