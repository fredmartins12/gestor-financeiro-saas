import os
import psycopg2
import psycopg2.extras # Essencial para retornar linhas como dicionários
import json
import csv
import io
from datetime import datetime, timedelta
from flask import Flask, jsonify, request, render_template, g, Response, redirect, url_for, flash
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, UserMixin, login_user, logout_user, current_user, login_required

# --- Configuração Inicial ---
app = Flask(__name__)
# A chave secreta agora é lida do ambiente, com um valor padrão para testes locais
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', '564312')
DATABASE_URL = os.environ.get('DATABASE_URL') # Pega a URL do banco de dados do ambiente do Render

# --- Configuração do Flask-Login ---
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# --- Conexão com o Banco de Dados (PostgreSQL) ---
def get_db():
    """Obtém a conexão com o DB, criando-a se necessário. Conexão é armazenada no contexto 'g'."""
    db = getattr(g, '_database', None)
    if db is None:
        if not DATABASE_URL:
            # Garante que o app não inicie sem a URL do DB em ambiente de produção
            raise EnvironmentError("DATABASE_URL não configurada.")
        db = g._database = psycopg2.connect(DATABASE_URL)
    return db

@app.teardown_appcontext
def close_connection(exception):
    """Fecha a conexão com o DB no final do request."""
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
    """Carrega o usuário a partir do ID para o Flask-Login."""
    try:
        with get_db().cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
            cursor.execute("SELECT * FROM usuarios WHERE id = %s", (user_id,))
            user_row = cursor.fetchone()
        if user_row:
            return User(id=user_row['id'], email=user_row['email'])
        return None
    except Exception:
        # Se houver erro de DB durante o carregamento, retorna None para falhar o login.
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
        try:
            with db: # Garante commit ou rollback
                with db.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                    # 1. Verifica se o email já existe
                    cursor.execute("SELECT id FROM usuarios WHERE email = %s", (email,))
                    if cursor.fetchone():
                        flash('Este email já está cadastrado.', 'error')
                        return redirect(url_for('register'))
                        
                    # 2. Validação simples de senha
                    if len(password) < 8:
                        flash('A senha deve ter no mínimo 8 caracteres.', 'error')
                        return redirect(url_for('register'))

                    # 3. Insere novo usuário
                    password_hash = generate_password_hash(password, method='pbkdf2:sha256')
                    cursor.execute("INSERT INTO usuarios (email, senha_hash) VALUES (%s, %s)", (email, password_hash))
            flash('Conta criada com sucesso! Faça o login.', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            flash(f'Erro ao registrar: {str(e)}', 'error')
            return redirect(url_for('register'))
            
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
    """Retorna o ID do usuário logado."""
    return current_user.id

# --- API Endpoints (Protegidos) ---

@app.route('/api/dados-iniciais', methods=['GET'])
@login_required
def get_dados_iniciais():
    user_id = get_current_user_id()
    db = get_db()
    
    def format_row(row):
        # Converte a linha do DictCursor para dict
        return dict(row)

    try:
        with db.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
            # Contas ativas
            cursor.execute("SELECT * FROM contas WHERE user_id = %s AND ativa = TRUE ORDER BY nome", (user_id,))
            contas = cursor.fetchall()

            # Operações de aposta ativas
            cursor.execute("SELECT t.*, c.nome as nome_conta FROM transacoes t JOIN contas c ON t.conta_id = c.id WHERE t.user_id = %s AND t.tipo = 'bet_placed' AND t.detalhes->>'status' = 'ativa'", (user_id,))
            operacoes_ativas = cursor.fetchall()

            # Histórico recente
            cursor.execute("SELECT t.*, c.nome as nome_conta FROM transacoes t JOIN contas c ON t.conta_id = c.id WHERE t.user_id = %s ORDER BY t.data_criacao DESC LIMIT 30", (user_id,))
            historico = cursor.fetchall()

            # Resumo do mês
            now = datetime.now()
            start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            
            # Entradas e Saídas (exceto apostas e transferências)
            cursor.execute("SELECT SUM(CASE WHEN valor > 0 THEN valor ELSE 0 END) as creditos, SUM(CASE WHEN valor < 0 THEN valor ELSE 0 END) as debitos FROM transacoes WHERE user_id = %s AND data_criacao >= %s AND tipo NOT IN ('bet_placed', 'bet_won', 'transfer_out', 'transfer_in')", (user_id, start_of_month))
            resumo_mes_transacoes = cursor.fetchone()
            
            # Lucro/Prejuízo do Mês (apenas bet_placed e bet_won)
            cursor.execute("SELECT SUM(valor) as lucro_prejuizo FROM transacoes WHERE user_id = %s AND data_criacao >= %s AND tipo IN ('bet_placed', 'bet_won')", (user_id, start_of_month))
            lucro_prejuizo_mes = cursor.fetchone()['lucro_prejuizo'] or 0

        return jsonify({
            'contas': [format_row(row) for row in contas], 
            'operacoesAtivas': [format_row(row) for row in operacoes_ativas], 
            'historico': [format_row(row) for row in historico],
            'resumoFinanceiro': { 
                'monthly_credits': float(resumo_mes_transacoes['creditos'] or 0), 
                'monthly_debits': float(resumo_mes_transacoes['debitos'] or 0), 
                'monthly_net': float(lucro_prejuizo_mes) 
            }
        })
    except Exception as e:
        return jsonify({'error': f'Erro ao buscar dados iniciais: {str(e)}'}), 500

@app.route('/api/contas', methods=['POST'])
@login_required
def add_conta():
    user_id, data = get_current_user_id(), request.get_json()
    db = get_db()
    try:
        with db: # Garante commit ou rollback
            with db.cursor() as cursor:
                cursor.execute("INSERT INTO contas (user_id, nome, casa_de_aposta, saldo, saldo_freebets, meta, volume_clube, dia_pagamento, valor_pagamento, observacoes, data_ultimo_codigo) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (user_id, data.get('nome'), data.get('casaDeAposta'), float(data.get('saldo', 0)), float(data.get('saldoFreebets', 0)), float(data.get('meta', 100)), float(data.get('volumeClube', 0)), data.get('diaPagamento'), float(data.get('valorPagamento', 0)), data.get('observacoes'), data.get('dataUltimoCodigo')))
        return jsonify({'message': 'Conta criada com sucesso'}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/contas/<int:conta_id>', methods=['PUT'])
@login_required
def update_conta(conta_id):
    user_id, data = get_current_user_id(), request.get_json()
    db = get_db()
    try:
        with db: # Garante commit ou rollback
            with db.cursor() as cursor:
                cursor.execute("UPDATE contas SET nome=%s, casa_de_aposta=%s, saldo=%s, saldo_freebets=%s, meta=%s, volume_clube=%s, dia_pagamento=%s, valor_pagamento=%s, observacoes=%s, ultimo_periodo_pago=%s, data_ultimo_codigo=%s WHERE id = %s AND user_id = %s",
                    (data.get('nome'), data.get('casaDeAposta'), float(data.get('saldo', 0)), float(data.get('saldoFreebets', 0)), float(data.get('meta', 0)), float(data.get('volumeClube', 0)), data.get('diaPagamento'), float(data.get('valorPagamento', 0)), data.get('observacoes'), data.get('ultimoPeriodoPago'), data.get('dataUltimoCodigo'), conta_id, user_id))
                rowcount = cursor.rowcount
        return jsonify({'message': 'Conta atualizada com sucesso'}) if rowcount > 0 else (jsonify({'error': 'Conta não encontrada'}), 404)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/contas/<int:conta_id>', methods=['DELETE'])
@login_required
def deactivate_conta(conta_id):
    user_id = get_current_user_id()
    db = get_db()
    try:
        with db: # Garante commit ou rollback
            with db.cursor() as cursor:
                # Desativa a conta (ativa = FALSE)
                cursor.execute("UPDATE contas SET ativa = FALSE WHERE id = %s AND user_id = %s", (conta_id, user_id))
                rowcount = cursor.rowcount
        return jsonify({'message': 'Conta desativada com sucesso'}) if rowcount > 0 else (jsonify({'error': 'Conta não encontrada'}), 404)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/operacoes', methods=['POST'])
@login_required
def registrar_operacao():
    user_id, op_data = get_current_user_id(), request.get_json()
    db = get_db()
    try:
        with db: # Garante commit ou rollback
            with db.cursor() as cursor:
                operation_id = f"op_{int(datetime.now().timestamp())}"
                
                if not op_data.get('legs'):
                     return jsonify({'error': 'Nenhuma "leg" de aposta fornecida'}), 400

                for leg in op_data.get('legs', []):
                    odd = float(leg.get('odd'))
                    
                    for bet in leg.get('accounts', []):
                        conta_id, stake = int(bet.get('accountId')), float(bet.get('stake'))
                        is_freebet = bet.get('isFreebet', False)
                        
                        # 1. Atualiza saldo
                        if is_freebet:
                            # Aposta com Freebet: debita de saldo_freebets
                            cursor.execute("UPDATE contas SET saldo_freebets = saldo_freebets - %s WHERE id = %s AND user_id = %s", (stake, conta_id, user_id))
                            valor_transacao = 0 
                        else:
                            # Aposta com Saldo: debita de saldo
                            cursor.execute("UPDATE contas SET saldo = saldo - %s WHERE id = %s AND user_id = %s", (stake, conta_id, user_id))
                            valor_transacao = -stake 

                        if cursor.rowcount == 0:
                            # Rollback automático devido ao 'with db:' se a conta não existir
                            return jsonify({'error': f'Conta {conta_id} não encontrada ou não pertence ao usuário.'}), 404

                        # 2. Registra transação 'bet_placed'
                        detalhes = json.dumps({'operationId': operation_id, 'result': leg.get('result'), 'category': op_data.get('category'),'odd': odd, 'stake': stake, 'isFreebet': is_freebet, 'status': 'ativa'})
                        cursor.execute("INSERT INTO transacoes (conta_id, user_id, tipo, valor, descricao, detalhes) VALUES (%s, %s, %s, %s, %s, %s)", 
                                        (conta_id, user_id, 'bet_placed', valor_transacao, f"{op_data.get('gameName')} - {leg.get('result')}", detalhes))
                        
        return jsonify({'message': 'Operação registrada com sucesso!'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/operacoes/resolver', methods=['POST'])
@login_required
def resolver_operacao():
    user_id, data = get_current_user_id(), request.get_json()
    operation_id, winning_market = data.get('operationId'), data.get('winningMarket')
    db = get_db()
    
    if not operation_id:
        return jsonify({'error': 'operationId é obrigatório'}), 400

    try:
        with db: # Garante commit ou rollback
            with db.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                # 1. Busca apostas ativas
                cursor.execute("SELECT * FROM transacoes WHERE user_id = %s AND tipo = 'bet_placed' AND detalhes->>'operationId' = %s AND detalhes->>'status' = 'ativa'", (user_id, operation_id))
                apostas = cursor.fetchall()
                
                if not apostas:
                    return jsonify({'error': 'Operação não encontrada ou já resolvida'}), 404

                # 2. Processa cada aposta (leg)
                for aposta in apostas:
                    detalhes = dict(aposta['detalhes'])
                    stake = detalhes.get('stake', 0.0)
                    odd = detalhes.get('odd', 1.0)
                    is_freebet = detalhes.get('isFreebet', False)
                    
                    is_winner = detalhes.get('result') == winning_market
                    
                    if is_winner:
                        detalhes['status'] = 'ganha'
                        # Cálculo do retorno: Stake * Odd
                        retorno_bruto = stake * odd
                        # Lucro/Retorno líquido: Se Freebet, tira o valor da Stake. Se Saldo, o Stake já foi contabilizado como perda (-stake)
                        retorno_liquido = retorno_bruto - (stake if is_freebet else 0.0)
                        
                        # Atualiza saldo na conta
                        cursor.execute("UPDATE contas SET saldo = saldo + %s WHERE id = %s", (retorno_liquido, aposta['conta_id']))
                        
                        # Insere a transação de ganho ('bet_won')
                        cursor.execute("INSERT INTO transacoes (conta_id, user_id, tipo, valor, descricao, detalhes) VALUES (%s, %s, %s, %s, %s, %s)", 
                                        (aposta['conta_id'], user_id, 'bet_won', retorno_liquido, f"Ganho: {aposta['descricao']}", json.dumps(detalhes)))
                    else:
                        detalhes['status'] = 'perdida'
                    
                    # 3. Atualiza a transação 'bet_placed' original (muda o status)
                    cursor.execute("UPDATE transacoes SET detalhes = %s WHERE id = %s", (json.dumps(detalhes), aposta['id']))
                    
        return jsonify({'message': 'Operação resolvida com sucesso!'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/transacoes/generico', methods=['POST'])
@login_required
def add_transacao_generica():
    user_id, data = get_current_user_id(), request.get_json()
    conta_id, tipo, valor_str, descricao = data.get('accountId'), data.get('type'), data.get('amount'), data.get('description')
    
    try:
        valor = float(valor_str)
        if valor <= 0: return jsonify({'error': 'Valor deve ser positivo'}), 400
    except (ValueError, TypeError):
        return jsonify({'error': 'Valor inválido'}), 400

    # Determina o valor que realmente afeta o saldo (positivo ou negativo)
    if tipo in ['deposit', 'bonus', 'other_credit']:
        valor_real = valor
    elif tipo in ['withdraw', 'expense', 'payment']:
        valor_real = -valor
    else:
        return jsonify({'error': 'Tipo de transação inválido'}), 400
        
    db = get_db()
    try:
        with db: # Garante commit ou rollback
            with db.cursor() as cursor:
                # 1. Atualiza o saldo
                cursor.execute("UPDATE contas SET saldo = saldo + %s WHERE id = %s AND user_id = %s", (valor_real, conta_id, user_id))
                if cursor.rowcount == 0:
                    return jsonify({'error': 'Conta não encontrada'}), 404
                    
                # 2. Insere a transação
                cursor.execute("INSERT INTO transacoes (conta_id, user_id, tipo, valor, descricao) VALUES (%s, %s, %s, %s, %s)", 
                               (conta_id, user_id, tipo, valor_real, descricao))
        return jsonify({'message': 'Transação registrada com sucesso!'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/transferencia', methods=['POST'])
@login_required
def transferencia_entre_contas():
    user_id, data = get_current_user_id(), request.get_json()
    from_id, to_id, valor_str, descricao = data.get('fromId'), data.get('toId'), data.get('amount'), data.get('description')

    if from_id == to_id:
         return jsonify({'error': 'As contas de origem e destino devem ser diferentes'}), 400

    try:
        valor = float(valor_str)
        if valor <= 0: return jsonify({'error': 'Valor deve ser positivo'}), 400
    except (ValueError, TypeError):
        return jsonify({'error': 'Valor inválido'}), 400

    db = get_db()
    try:
        with db: # Garante commit ou rollback
            with db.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                # 1. Debita da conta de origem
                cursor.execute("UPDATE contas SET saldo = saldo - %s WHERE id = %s AND user_id = %s", (valor, from_id, user_id))
                if cursor.rowcount == 0: return jsonify({'error': 'Conta de origem não encontrada'}), 404
                
                # 2. Credita na conta de destino
                cursor.execute("UPDATE contas SET saldo = saldo + %s WHERE id = %s AND user_id = %s", (valor, to_id, user_id))
                if cursor.rowcount == 0: return jsonify({'error': 'Conta de destino não encontrada'}), 404

                # 3. Busca nomes para descrição
                cursor.execute("SELECT nome FROM contas WHERE id = %s", (from_id,))
                from_name = cursor.fetchone()['nome']
                cursor.execute("SELECT nome FROM contas WHERE id = %s", (to_id,))
                to_name = cursor.fetchone()['nome']
                
                # 4. Insere transação de saída (e obtém o ID)
                cursor.execute("INSERT INTO transacoes (conta_id, user_id, tipo, valor, descricao, detalhes) VALUES (%s, %s, %s, %s, %s, %s) RETURNING id", 
                               (from_id, user_id, 'transfer_out', -valor, f"Para: {to_name} ({descricao})", json.dumps({'linked_transfer_id': None})))
                transfer_out_id = cursor.fetchone()['id']
                
                # 5. Insere transação de entrada (e obtém o ID)
                cursor.execute("INSERT INTO transacoes (conta_id, user_id, tipo, valor, descricao, detalhes) VALUES (%s, %s, %s, %s, %s, %s) RETURNING id", 
                               (to_id, user_id, 'transfer_in', valor, f"De: {from_name} ({descricao})", json.dumps({'linked_transfer_id': transfer_out_id})))
                transfer_in_id = cursor.fetchone()['id']
                
                # 6. Atualiza a transação de saída com o ID da transação de entrada para facilitar a reversão
                cursor.execute("UPDATE transacoes SET detalhes = %s WHERE id = %s", (json.dumps({'linked_transfer_id': transfer_in_id}), transfer_out_id))

        return jsonify({'message': 'Transferência realizada com sucesso!'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/transacoes/<int:transacao_id>', methods=['DELETE'])
@login_required
def reverter_transacao(transacao_id):
    """
    Reverte uma transação e todos os seus efeitos no saldo e freebets.
    No caso de Apostas (bet_placed/bet_won), reverte todas as transações da mesma operação (operationId).
    No caso de Transferências, reverte a transação linkada.
    """
    user_id = get_current_user_id()
    db = get_db()
    
    try:
        with db: # Garante commit ou rollback
            with db.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                # 1. Busca a transação inicial
                cursor.execute("SELECT * FROM transacoes WHERE id = %s AND user_id = %s", (transacao_id, user_id))
                transacao = cursor.fetchone()
                if not transacao: return jsonify({'error': 'Transação não encontrada'}), 404

                transacoes_para_reverter = [transacao]
                detalhes = transacao['detalhes'] if transacao['detalhes'] else {}
                
                # 2. Lógica para transações agrupadas (Apostas ou Transferências)
                if transacao['tipo'] in ['bet_placed', 'bet_won']:
                    # Reverte TODAS as transações relacionadas à mesma operação
                    operation_id = detalhes.get('operationId')
                    if operation_id:
                        cursor.execute("SELECT * FROM transacoes WHERE user_id = %s AND detalhes->>'operationId' = %s", (user_id, operation_id))
                        apostas_relacionadas = cursor.fetchall()
                        transacoes_para_reverter = list(apostas_relacionadas)

                elif transacao['tipo'] in ['transfer_in', 'transfer_out']:
                    # Reverte a transação e a transação de contrapartida (linkada)
                    linked_id = detalhes.get('linked_transfer_id')
                    
                    # Se for transfer_out, o linked_id aponta para transfer_in. Se for transfer_in, o linked_id aponta para transfer_out.
                    id_to_find = linked_id if linked_id else None
                    if id_to_find:
                        cursor.execute("SELECT * FROM transacoes WHERE id = %s AND user_id = %s", (id_to_find, user_id))
                        linked_transacao = cursor.fetchone()
                        if linked_transacao:
                            transacoes_para_reverter.append(linked_transacao)
                        
                        # Remove duplicatas (se a transação inicial e a linkada forem a mesma, o que não deve ocorrer)
                        transacoes_para_reverter = list({t['id']: t for t in transacoes_para_reverter}.values())
                
                # 3. Executa a reversão de saldo e deleta as transações
                for t in transacoes_para_reverter:
                    valor_reverter = -t['valor'] # Valor a adicionar/subtrair para reverter o efeito
                    t_detalhes = t['detalhes'] if t['detalhes'] else {}
                    
                    if t['tipo'] == 'bet_placed':
                        # Se for aposta ativa (stake): devolve o stake. Se for freebet ativa: devolve a freebet.
                        if t_detalhes.get('isFreebet') and t_detalhes.get('status') == 'ativa':
                            cursor.execute("UPDATE contas SET saldo_freebets = saldo_freebets + %s WHERE id = %s", (t_detalhes.get('stake', 0.0), t['conta_id']))
                        # Se não for freebet E o valor registrado for negativo (stake retirado):
                        elif t['valor'] < 0:
                            cursor.execute("UPDATE contas SET saldo = saldo + %s WHERE id = %s", (valor_reverter, t['conta_id']))
                        # Se o valor for 0 (freebet resolvida ou aposta perdida resolvida) não faz nada no saldo aqui, a correção é feita na exclusão do bet_won
                            
                    elif t['tipo'] == 'bet_won':
                        # Se bet_won (valor positivo), valor_reverter é negativo, retira o lucro do saldo.
                        cursor.execute("UPDATE contas SET saldo = saldo + %s WHERE id = %s", (valor_reverter, t['conta_id']))
                        
                    elif t['tipo'] in ['deposit', 'withdraw', 'expense', 'payment', 'transfer_in', 'transfer_out', 'bonus', 'other_credit']:
                        # Para transações genéricas e transferências: reverte o valor no saldo.
                        cursor.execute("UPDATE contas SET saldo = saldo + %s WHERE id = %s", (valor_reverter, t['conta_id']))

                    # Deleta a transação do banco
                    cursor.execute("DELETE FROM transacoes WHERE id = %s", (t['id'],))
                    
                total_revertidas = len(transacoes_para_reverter)
        
        return jsonify({'message': f'{total_revertidas} transações e seus efeitos foram revertidos com sucesso!'})
        
    except Exception as e:
        return jsonify({'error': f'Erro ao reverter transação: {str(e)}'}), 500

@app.route('/api/backup', methods=['GET'])
@login_required
def backup_dados():
    user_id = get_current_user_id()
    try:
        with get_db().cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
            cursor.execute("SELECT * FROM contas WHERE user_id = %s", (user_id,))
            contas = [dict(row) for row in cursor.fetchall()]
            cursor.execute("SELECT * FROM transacoes WHERE user_id = %s", (user_id,))
            transacoes = [dict(row) for row in cursor.fetchall()]
        backup_data = {'backupDate': datetime.now().isoformat(), 'contas': contas, 'transacoes': transacoes}
        return Response(json.dumps(backup_data, indent=2, default=str), mimetype='application/json', headers={'Content-Disposition': 'attachment;filename=backup_gestao.json'})
    except Exception as e:
        return jsonify({'error': f'Erro ao gerar backup: {str(e)}'}), 500

@app.route('/api/relatorio', methods=['GET'])
@login_required
def get_relatorio():
    user_id = get_current_user_id()
    year = request.args.get('year', default=datetime.now().year, type=int)
    month = request.args.get('month', default=datetime.now().month, type=int)
    start_date, end_date = datetime(year, month, 1), (datetime(year, month, 1) + timedelta(days=32)).replace(day=1)
    
    try:
        with get_db().cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
            cursor.execute("SELECT t.*, c.nome as nome_conta, c.casa_de_aposta FROM transacoes t JOIN contas c ON t.conta_id = c.id WHERE t.user_id = %s AND t.data_criacao >= %s AND t.data_criacao < %s", (user_id, start_date, end_date))
            transacoes = [dict(row) for row in cursor.fetchall()]
        
        # Processamento de análise em Python
        net_profit = sum(t['valor'] for t in transacoes if t['tipo'] in ['bet_placed', 'bet_won'])
        total_expenses = sum(t['valor'] for t in transacoes if t['tipo'] == 'expense')
        total_payments = sum(t['valor'] for t in transacoes if t['tipo'] == 'payment')

        analysis = {}
        for t in transacoes:
            if t['conta_id'] not in analysis: 
                analysis[t['conta_id']] = {'name': t['nome_conta'], 'profit': 0.0, 'wagered': 0.0, 'betCount': 0}
            
            if t['tipo'] in ['bet_placed', 'bet_won']: 
                analysis[t['conta_id']]['profit'] += t['valor']
                
            if t['tipo'] == 'bet_placed':
                details = t['detalhes'] if t['detalhes'] and isinstance(t['detalhes'], dict) else {}
                analysis[t['conta_id']]['wagered'] += details.get('stake', 0.0)
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
    except Exception as e:
        return jsonify({'error': f'Erro ao gerar relatório: {str(e)}'}), 500

@app.route('/api/contas/<int:conta_id>/pagar', methods=['POST'])
@login_required
def registrar_pagamento(conta_id):
    user_id = get_current_user_id()
    db = get_db()
    try:
        with db: # Garante commit ou rollback
            with db.cursor() as cursor:
                periodo_pago = datetime.now().strftime('%Y-%m')
                # Apenas atualiza o campo `ultimo_periodo_pago`
                cursor.execute("UPDATE contas SET ultimo_periodo_pago = %s WHERE id = %s AND user_id = %s", (periodo_pago, conta_id, user_id))
                rowcount = cursor.rowcount
        
        if rowcount > 0:
            return jsonify({'message': 'Pagamento registrado com sucesso!'})
        else:
            return jsonify({'error': 'Conta não encontrada'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/restore', methods=['POST'])
@login_required
def restore_backup():
    user_id = get_current_user_id()
    if 'backupFile' not in request.files: return jsonify({'error': 'Nenhum arquivo enviado'}), 400
    file = request.files['backupFile']
    if file.filename == '': return jsonify({'error': 'Nenhum arquivo selecionado'}), 400
        
    try:
        backup_data = json.load(file)
        contas = backup_data.get('contas', [])
        transacoes = backup_data.get('transacoes', [])
        db = get_db()
        
        with db: # Garante commit ou rollback
            with db.cursor() as cursor:
                # 1. Limpa dados existentes do usuário
                cursor.execute("DELETE FROM transacoes WHERE user_id = %s", (user_id,))
                cursor.execute("DELETE FROM contas WHERE user_id = %s", (user_id,))
                
                # 2. Restaura Contas
                for conta in contas:
                    # Usamos ON CONFLICT DO NOTHING se a chave 'id' for violada, o que é útil se o DB tiver sequências.
                    cursor.execute("""
                        INSERT INTO contas (id, user_id, nome, casa_de_aposta, saldo, saldo_freebets, meta, volume_clube, dia_pagamento, valor_pagamento, observacoes, ultimo_periodo_pago, ativa, data_ultimo_codigo)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (id) DO NOTHING
                    """, (conta.get('id'), user_id, conta.get('nome'), conta.get('casa_de_aposta'), conta.get('saldo'), conta.get('saldo_freebets'), conta.get('meta'), conta.get('volume_clube'), conta.get('dia_pagamento'), conta.get('valor_pagamento'), conta.get('observacoes'), conta.get('ultimo_periodo_pago'), conta.get('ativa', True), conta.get('data_ultimo_codigo')))
                
                # 3. Restaura Transações
                for transacao in transacoes:
                    detalhes = transacao.get('detalhes')
                    if isinstance(detalhes, str):
                        try: detalhes = json.loads(detalhes)
                        except json.JSONDecodeError: detalhes = {}

                    cursor.execute("""
                        INSERT INTO transacoes (id, conta_id, user_id, tipo, valor, descricao, detalhes, data_criacao)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (id) DO NOTHING
                    """, (transacao.get('id'), transacao.get('conta_id'), user_id, transacao.get('tipo'), transacao.get('valor'), transacao.get('descricao'), json.dumps(detalhes), transacao.get('data_criacao')))
                    
        return jsonify({'message': f'{len(contas)} contas e {len(transacoes)} transações restauradas com sucesso!'})
    except Exception as e:
        return jsonify({'error': f'Erro ao processar o backup: {str(e)}'}), 500

@app.route('/api/import-csv', methods=['POST'])
@login_required
def import_csv():
    user_id = get_current_user_id()
    if 'csvFile' not in request.files: return jsonify({'error': 'Nenhum arquivo CSV enviado'}), 400
    file = request.files['csvFile']
    if file.filename == '': return jsonify({'error': 'Nenhum arquivo selecionado'}), 400
    
    try:
        stream = io.StringIO(file.stream.read().decode("UTF-8"), newline=None)
        csv_reader = csv.DictReader(stream)
        contas_para_processar = list(csv_reader)
        criadas = 0
        atualizadas = 0
        db = get_db()
        
        with db: # Garante commit ou rollback
            with db.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                for conta_data in contas_para_processar:
                    nome = conta_data.get('nome', '').strip()
                    if not nome: continue
                    
                    cursor.execute("SELECT id FROM contas WHERE nome = %s AND user_id = %s", (nome, user_id))
                    conta_existente = cursor.fetchone()
                    
                    # Tenta converter para os tipos corretos, usando valores padrão em caso de erro.
                    dados = {
                        "nome": nome, 
                        "casa_de_aposta": conta_data.get('casa_de_aposta') or None, 
                        "saldo": float(conta_data.get('saldo') or 0), 
                        "saldo_freebets": float(conta_data.get('saldo_freebets') or 0), 
                        "dia_pagamento": int(conta_data.get('dia_pagamento')) if conta_data.get('dia_pagamento') and conta_data.get('dia_pagamento').isdigit() else None, 
                        "valor_pagamento": float(conta_data.get('valor_pagamento') or 0), 
                        "observacoes": conta_data.get('observacoes') or None, 
                        "data_ultimo_codigo": conta_data.get('data_ultimo_codigo') or None,
                    }
                    
                    if conta_existente:
                        # Atualiza conta existente
                        cursor.execute("""
                            UPDATE contas SET casa_de_aposta=%s, saldo=%s, saldo_freebets=%s, dia_pagamento=%s, valor_pagamento=%s, observacoes=%s, data_ultimo_codigo=%s
                            WHERE id = %s AND user_id = %s
                        """, (dados['casa_de_aposta'], dados['saldo'], dados['saldo_freebets'], dados['dia_pagamento'], dados['valor_pagamento'], dados['observacoes'], dados['data_ultimo_codigo'], conta_existente['id'], user_id))
                        atualizadas += 1
                    else:
                        # Insere nova conta
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
    # Usado para execução local
    app.run(debug=True)
