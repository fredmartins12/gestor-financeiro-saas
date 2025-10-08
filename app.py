import os
import psycopg2
import psycopg2.extras
import json
import csv
import io
import re
from datetime import datetime, timedelta
from functools import wraps
from contextlib import contextmanager
from flask import Flask, jsonify, request, render_template, g, Response, redirect, url_for, flash, abort
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, UserMixin, login_user, logout_user, current_user, login_required

# --- Configuração Inicial ---
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', '564312')
DATABASE_URL = os.environ.get('DATABASE_URL')

# --- Configuração do Flask-Login ---
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# --- Context Manager para Transações ---
@contextmanager
def db_transaction():
    db = get_db()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise

# --- Validações ---
def validar_email(email):
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def validar_valor_positivo(valor):
    return isinstance(valor, (int, float)) and valor >= 0

def conta_pertence_ao_usuario(conta_id, user_id):
    with get_db().cursor() as cursor:
        cursor.execute("SELECT id FROM contas WHERE id = %s AND user_id = %s", (conta_id, user_id))
        return cursor.fetchone() is not None

def transacao_pertence_ao_usuario(transacao_id, user_id):
    with get_db().cursor() as cursor:
        cursor.execute("SELECT id FROM transacoes WHERE id = %s AND user_id = %s", (transacao_id, user_id))
        return cursor.fetchone() is not None

# --- Decorators de Validação ---
def validar_json_campos(campos_obrigatorios):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not request.is_json:
                return jsonify({'error': 'Content-Type deve ser application/json'}), 400
            
            data = request.get_json()
            campos_faltantes = [campo for campo in campos_obrigatorios if campo not in data]
            if campos_faltantes:
                return jsonify({'error': f'Campos obrigatórios faltando: {", ".join(campos_faltantes)}'}), 400
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

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
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        
        if not email or not password:
            flash('Email e senha são obrigatórios.', 'error')
            return render_template('login.html')
        
        if not validar_email(email):
            flash('Formato de email inválido.', 'error')
            return render_template('login.html')
        
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
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        
        if not email or not password:
            flash('Email e senha são obrigatórios.', 'error')
            return redirect(url_for('register'))
        
        if not validar_email(email):
            flash('Formato de email inválido.', 'error')
            return redirect(url_for('register'))
        
        if len(password) < 8:
            flash('A senha deve ter no mínimo 8 caracteres.', 'error')
            return redirect(url_for('register'))
        
        db = get_db()
        try:
            with db.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                cursor.execute("SELECT id FROM usuarios WHERE email = %s", (email,))
                if cursor.fetchone():
                    flash('Este email já está cadastrado.', 'error')
                    return redirect(url_for('register'))
                
                password_hash = generate_password_hash(password, method='pbkdf2:sha256')
                cursor.execute("INSERT INTO usuarios (email, senha_hash) VALUES (%s, %s)", (email, password_hash))
            db.commit()
            flash('Conta criada com sucesso! Faça o login.', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            db.rollback()
            flash('Erro interno ao criar conta.', 'error')
    
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
    
    with get_db().cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
        # Contas ativas
        cursor.execute("SELECT * FROM contas WHERE user_id = %s AND ativa = TRUE ORDER BY nome", (user_id,))
        contas = [dict(row) for row in cursor.fetchall()]
        
        # Operações ativas
        cursor.execute("""
            SELECT t.*, c.nome as nome_conta 
            FROM transacoes t 
            JOIN contas c ON t.conta_id = c.id 
            WHERE t.user_id = %s AND t.tipo = 'bet_placed' 
            AND t.detalhes->>'status' = 'ativa'
        """, (user_id,))
        operacoes_ativas = [dict(row) for row in cursor.fetchall()]
        
        # Histórico recente
        cursor.execute("""
            SELECT t.*, c.nome as nome_conta 
            FROM transacoes t 
            JOIN contas c ON t.conta_id = c.id 
            WHERE t.user_id = %s 
            ORDER BY t.data_criacao DESC 
            LIMIT 30
        """, (user_id,))
        historico = [dict(row) for row in cursor.fetchall()]
        
        # Resumo mensal otimizado
        start_of_month = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        cursor.execute("""
            SELECT 
                SUM(CASE WHEN valor > 0 AND tipo NOT IN ('bet_placed', 'bet_won') THEN valor ELSE 0 END) as entradas,
                SUM(CASE WHEN valor < 0 AND tipo NOT IN ('bet_placed', 'bet_won') THEN valor ELSE 0 END) as saidas,
                SUM(CASE WHEN tipo IN ('bet_placed', 'bet_won') THEN valor ELSE 0 END) as lucro_prejuizo
            FROM transacoes 
            WHERE user_id = %s 
            AND data_criacao >= %s
        """, (user_id, start_of_month))
        resumo = cursor.fetchone()
    
    return jsonify({
        'contas': contas, 
        'operacoesAtivas': operacoes_ativas, 
        'historico': historico,
        'resumoFinanceiro': { 
            'monthly_credits': float(resumo['entradas'] or 0), 
            'monthly_debits': float(abs(resumo['saidas'] or 0)), 
            'monthly_net': float(resumo['lucro_prejuizo'] or 0) 
        }
    })

@app.route('/api/contas', methods=['POST'])
@login_required
@validar_json_campos(['nome'])
def add_conta():
    user_id = get_current_user_id()
    data = request.get_json()
    
    if not conta_pertence_ao_usuario(data.get('conta_id'), user_id) if data.get('conta_id') else True:
        return jsonify({'error': 'Acesso não autorizado'}), 403
    
    try:
        with db_transaction() as db:
            with db.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO contas 
                    (user_id, nome, casa_de_aposta, saldo, saldo_freebets, meta, volume_clube, dia_pagamento, valor_pagamento, observacoes, data_ultimo_codigo) 
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    user_id, data.get('nome'), data.get('casaDeAposta'), 
                    data.get('saldo', 0), data.get('saldoFreebets', 0), 
                    data.get('meta', 100), data.get('volumeClube', 0), 
                    data.get('diaPagamento'), data.get('valorPagamento'), 
                    data.get('observacoes'), data.get('dataUltimoCodigo')
                ))
        return jsonify({'message': 'Conta criada com sucesso'}), 201
    except Exception as e:
        return jsonify({'error': f'Erro ao criar conta: {str(e)}'}), 500

@app.route('/api/contas/<int:conta_id>', methods=['PUT'])
@login_required
@validar_json_campos(['nome'])
def update_conta(conta_id):
    user_id = get_current_user_id()
    data = request.get_json()
    
    if not conta_pertence_ao_usuario(conta_id, user_id):
        return jsonify({'error': 'Conta não encontrada'}), 404
    
    try:
        with db_transaction() as db:
            with db.cursor() as cursor:
                cursor.execute("""
                    UPDATE contas SET 
                    nome=%s, casa_de_aposta=%s, saldo=%s, saldo_freebets=%s, meta=%s, 
                    volume_clube=%s, dia_pagamento=%s, valor_pagamento=%s, observacoes=%s, 
                    ultimo_periodo_pago=%s, data_ultimo_codigo=%s 
                    WHERE id = %s AND user_id = %s
                """, (
                    data.get('nome'), data.get('casaDeAposta'), data.get('saldo'), 
                    data.get('saldoFreebets'), data.get('meta'), data.get('volumeClube'), 
                    data.get('diaPagamento'), data.get('valorPagamento'), data.get('observacoes'), 
                    data.get('ultimoPeriodoPago'), data.get('dataUltimoCodigo'), 
                    conta_id, user_id
                ))
                
                if cursor.rowcount == 0:
                    return jsonify({'error': 'Conta não encontrada'}), 404
        
        return jsonify({'message': 'Conta atualizada com sucesso'})
    except Exception as e:
        return jsonify({'error': f'Erro ao atualizar conta: {str(e)}'}), 500

@app.route('/api/contas/<int:conta_id>', methods=['DELETE'])
@login_required
def deactivate_conta(conta_id):
    user_id = get_current_user_id()
    
    if not conta_pertence_ao_usuario(conta_id, user_id):
        return jsonify({'error': 'Conta não encontrada'}), 404
    
    try:
        with db_transaction() as db:
            with db.cursor() as cursor:
                cursor.execute("UPDATE contas SET ativa = FALSE WHERE id = %s AND user_id = %s", (conta_id, user_id))
                
                if cursor.rowcount == 0:
                    return jsonify({'error': 'Conta não encontrada'}), 404
        
        return jsonify({'message': 'Conta desativada com sucesso'})
    except Exception as e:
        return jsonify({'error': f'Erro ao desativar conta: {str(e)}'}), 500

@app.route('/api/transacoes', methods=['GET'])
@login_required
def listar_transacoes():
    user_id = get_current_user_id()
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 50, type=int), 100)  # Limite de 100 por página
    offset = (page - 1) * per_page
    
    with get_db().cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
        cursor.execute("""
            SELECT t.*, c.nome AS nome_conta 
            FROM transacoes t 
            JOIN contas c ON t.conta_id = c.id 
            WHERE t.user_id = %s 
            ORDER BY t.data_criacao DESC 
            LIMIT %s OFFSET %s
        """, (user_id, per_page, offset))
        transacoes = [dict(row) for row in cursor.fetchall()]
        
        # Contar total para paginação
        cursor.execute("SELECT COUNT(*) as total FROM transacoes WHERE user_id = %s", (user_id,))
        total = cursor.fetchone()['total']
    
    return jsonify({
        'transacoes': transacoes,
        'pagination': {
            'page': page,
            'per_page': per_page,
            'total': total,
            'pages': (total + per_page - 1) // per_page
        }
    })

@app.route('/api/transacoes', methods=['POST'])
@login_required
@validar_json_campos(['accountId', 'type', 'amount', 'description'])
def criar_transacao():
    user_id = get_current_user_id()
    data = request.get_json()
    
    conta_id = data.get('accountId')
    tipo = data.get('type')
    valor = float(data.get('amount'))
    descricao = data.get('description')
    
    if not validar_valor_positivo(valor):
        return jsonify({'error': 'Valor deve ser positivo'}), 400
    
    if not conta_pertence_ao_usuario(conta_id, user_id):
        return jsonify({'error': 'Conta não encontrada'}), 404
    
    valor_real = valor if tipo in ['deposit', 'bonus', 'other_credit'] else -valor
    
    try:
        with db_transaction() as db:
            with db.cursor() as cursor:
                cursor.execute("UPDATE contas SET saldo = saldo + %s WHERE id = %s", (valor_real, conta_id))
                cursor.execute("""
                    INSERT INTO transacoes (conta_id, user_id, tipo, valor, descricao) 
                    VALUES (%s, %s, %s, %s, %s)
                """, (conta_id, user_id, tipo, valor_real, descricao))
        
        return jsonify({'message': 'Transação registrada com sucesso!'})
    except Exception as e:
        return jsonify({'error': f'Erro ao registrar transação: {str(e)}'}), 500

@app.route('/api/transacoes/<int:transacao_id>', methods=['PUT'])
@login_required
@validar_json_campos(['type', 'amount', 'description'])
def editar_transacao(transacao_id):
    user_id = get_current_user_id()
    data = request.get_json()
    
    if not transacao_pertence_ao_usuario(transacao_id, user_id):
        return jsonify({'error': 'Transação não encontrada'}), 404
    
    try:
        with db_transaction() as db:
            with db.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                # Buscar transação original
                cursor.execute("SELECT * FROM transacoes WHERE id = %s", (transacao_id,))
                transacao = cursor.fetchone()
                if not transacao:
                    return jsonify({'error': 'Transação não encontrada'}), 404
                
                # Reverter valor antigo
                cursor.execute("UPDATE contas SET saldo = saldo - %s WHERE id = %s", 
                             (transacao['valor'], transacao['conta_id']))
                
                # Calcular novo valor
                novo_valor = float(data.get('amount', abs(transacao['valor'])))
                tipo = data.get('type', transacao['tipo'])
                valor_real = novo_valor if tipo in ['deposit', 'bonus', 'other_credit'] else -novo_valor
                descricao = data.get('description', transacao['descricao'])
                
                # Atualizar transação
                cursor.execute("""
                    UPDATE transacoes SET tipo = %s, valor = %s, descricao = %s 
                    WHERE id = %s
                """, (tipo, valor_real, descricao, transacao_id))
                
                # Aplicar novo valor
                cursor.execute("UPDATE contas SET saldo = saldo + %s WHERE id = %s", 
                             (valor_real, transacao['conta_id']))
        
        return jsonify({'message': 'Transação atualizada com sucesso!'})
    except Exception as e:
        return jsonify({'error': f'Erro ao atualizar transação: {str(e)}'}), 500

@app.route('/api/transacoes/<int:transacao_id>', methods=['DELETE'])
@login_required
def deletar_transacao(transacao_id):
    user_id = get_current_user_id()
    
    if not transacao_pertence_ao_usuario(transacao_id, user_id):
        return jsonify({'error': 'Transação não encontrada'}), 404
    
    try:
        with db_transaction() as db:
            with db.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                cursor.execute("SELECT * FROM transacoes WHERE id = %s", (transacao_id,))
                transacao = cursor.fetchone()
                
                if not transacao:
                    return jsonify({'error': 'Transação não encontrada'}), 404

                detalhes = transacao['detalhes'] or {}
                operation_id = detalhes.get('operationId')

                if operation_id:
                    # Reverter apostas relacionadas apenas da mesma conta
                    cursor.execute("""
                        SELECT * FROM transacoes 
                        WHERE user_id = %s AND detalhes->>'operationId' = %s AND conta_id = %s
                    """, (user_id, operation_id, transacao['conta_id']))
                    
                    apostas_relacionadas = cursor.fetchall()
                    for aposta in apostas_relacionadas:
                        aposta_detalhes = aposta['detalhes'] or {}
                        valor = aposta['valor']
                        
                        cursor.execute("UPDATE contas SET saldo = saldo - %s WHERE id = %s", 
                                     (valor, aposta['conta_id']))
                        
                        if aposta['tipo'] == 'bet_placed' and aposta_detalhes.get('isFreebet'):
                            cursor.execute("UPDATE contas SET saldo_freebets = saldo_freebets + %s WHERE id = %s", 
                                         (aposta_detalhes.get('stake', 0), aposta['conta_id']))
                        
                        cursor.execute("DELETE FROM transacoes WHERE id = %s", (aposta['id'],))
                else:
                    # Reverter transação normal
                    cursor.execute("UPDATE contas SET saldo = saldo - %s WHERE id = %s", 
                                 (transacao['valor'], transacao['conta_id']))
                    cursor.execute("DELETE FROM transacoes WHERE id = %s", (transacao_id,))
        
        return jsonify({'message': 'Transação revertida com sucesso!'})
    except Exception as e:
        return jsonify({'error': f'Erro ao reverter transação: {str(e)}'}), 500

@app.route('/api/operacoes', methods=['POST'])
@login_required
@validar_json_campos(['legs', 'gameName', 'category'])
def registrar_operacao():
    user_id = get_current_user_id()
    op_data = request.get_json()
    
    # Validar contas
    for leg in op_data.get('legs', []):
        for bet in leg.get('accounts', []):
            conta_id = int(bet.get('accountId'))
            if not conta_pertence_ao_usuario(conta_id, user_id):
                return jsonify({'error': f'Conta {conta_id} não encontrada'}), 404
    
    try:
        with db_transaction() as db:
            with db.cursor() as cursor:
                operation_id = f"op_{int(datetime.now().timestamp())}"
                
                for leg in op_data.get('legs', []):
                    for bet in leg.get('accounts', []):
                        conta_id = int(bet.get('accountId'))
                        stake = float(bet.get('stake'))
                        is_freebet = bet.get('isFreebet', False)
                        odd = float(leg.get('odd'))
                        
                        if not validar_valor_positivo(stake):
                            return jsonify({'error': 'Stake deve ser positivo'}), 400
                        
                        if is_freebet:
                            cursor.execute("UPDATE contas SET saldo_freebets = saldo_freebets - %s WHERE id = %s", 
                                         (stake, conta_id))
                        else:
                            cursor.execute("UPDATE contas SET saldo = saldo - %s WHERE id = %s", 
                                         (stake, conta_id))
                        
                        detalhes = json.dumps({
                            'operationId': operation_id, 
                            'result': leg.get('result'), 
                            'category': op_data.get('category'),
                            'odd': odd, 
                            'stake': stake, 
                            'isFreebet': is_freebet, 
                            'status': 'ativa'
                        })
                        
                        cursor.execute("""
                            INSERT INTO transacoes (conta_id, user_id, tipo, valor, descricao, detalhes) 
                            VALUES (%s, %s, %s, %s, %s, %s)
                        """, (
                            conta_id, user_id, 'bet_placed', 
                            -stake if not is_freebet else 0, 
                            f"{op_data.get('gameName')} - {leg.get('result')}", 
                            detalhes
                        ))
        
        return jsonify({'message': 'Operação registrada com sucesso!'})
    except Exception as e:
        return jsonify({'error': f'Erro ao registrar operação: {str(e)}'}), 500

@app.route('/api/operacoes/resolver', methods=['POST'])
@login_required
@validar_json_campos(['operationId'])
def resolver_operacao():
    user_id = get_current_user_id()
    data = request.get_json()
    operation_id = data.get('operationId')
    winning_market = data.get('winningMarket')
    
    try:
        with db_transaction() as db:
            with db.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                cursor.execute("""
                    SELECT * FROM transacoes 
                    WHERE user_id = %s AND tipo = 'bet_placed' 
                    AND detalhes->>'operationId' = %s AND detalhes->>'status' = 'ativa'
                """, (user_id, operation_id))
                
                apostas = cursor.fetchall()
                if not apostas:
                    return jsonify({'error': 'Operação não encontrada ou já resolvida'}), 404

                if winning_market is None:
                    # Marcar todas como perdidas
                    for aposta in apostas:
                        detalhes = dict(aposta['detalhes'])
                        detalhes['status'] = 'perdida'
                        cursor.execute("UPDATE transacoes SET detalhes = %s WHERE id = %s", 
                                     (json.dumps(detalhes), aposta['id']))
                    
                    return jsonify({'message': 'Operação marcada como perdida!'})

                # Processar apostas vencedoras/perdedoras
                for aposta in apostas:
                    detalhes = dict(aposta['detalhes'])
                    is_winner = detalhes.get('result') == winning_market
                    
                    if is_winner:
                        retorno = detalhes['stake'] * detalhes['odd']
                        if detalhes['isFreebet']:
                            retorno -= detalhes['stake']
                        
                        cursor.execute("UPDATE contas SET saldo = saldo + %s WHERE id = %s", 
                                     (retorno, aposta['conta_id']))
                        
                        cursor.execute("""
                            INSERT INTO transacoes (conta_id, user_id, tipo, valor, descricao, detalhes) 
                            VALUES (%s, %s, %s, %s, %s, %s)
                        """, (
                            aposta['conta_id'], user_id, 'bet_won', retorno, 
                            f"Ganho: {aposta['descricao']}", 
                            json.dumps(detalhes)
                        ))
                        detalhes['status'] = 'ganha'
                    else:
                        detalhes['status'] = 'perdida'
                    
                    cursor.execute("UPDATE transacoes SET detalhes = %s WHERE id = %s", 
                                 (json.dumps(detalhes), aposta['id']))
        
        return jsonify({'message': 'Operação resolvida com sucesso!'})
    except Exception as e:
        return jsonify({'error': f'Erro ao resolver operação: {str(e)}'}), 500

@app.route('/api/transacoes/generico', methods=['POST'])
@login_required
@validar_json_campos(['accountId', 'type', 'amount', 'description'])
def add_transacao_generica():
    user_id = get_current_user_id()
    data = request.get_json()
    
    conta_id = data.get('accountId')
    tipo = data.get('type')
    valor = float(data.get('amount'))
    descricao = data.get('description')
    
    if not validar_valor_positivo(valor):
        return jsonify({'error': 'Valor deve ser positivo'}), 400
    
    if not conta_pertence_ao_usuario(conta_id, user_id):
        return jsonify({'error': 'Conta não encontrada'}), 404
    
    valor_real = valor if tipo in ['deposit', 'bonus', 'other_credit'] else -valor
    
    try:
        with db_transaction() as db:
            with db.cursor() as cursor:
                cursor.execute("UPDATE contas SET saldo = saldo + %s WHERE id = %s", (valor_real, conta_id))
                cursor.execute("""
                    INSERT INTO transacoes (conta_id, user_id, tipo, valor, descricao) 
                    VALUES (%s, %s, %s, %s, %s)
                """, (conta_id, user_id, tipo, valor_real, descricao))
        
        return jsonify({'message': 'Transação registrada com sucesso!'})
    except Exception as e:
        return jsonify({'error': f'Erro ao registrar transação: {str(e)}'}), 500

@app.route('/api/transferencia', methods=['POST'])
@login_required
@validar_json_campos(['fromId', 'toId', 'amount', 'description'])
def transferencia_entre_contas():
    user_id = get_current_user_id()
    data = request.get_json()
    
    from_id = data.get('fromId')
    to_id = data.get('toId')
    valor = float(data.get('amount'))
    descricao = data.get('description')
    
    if not validar_valor_positivo(valor):
        return jsonify({'error': 'Valor deve ser positivo'}), 400
    
    if from_id == to_id:
        return jsonify({'error': 'Conta de origem e destino devem ser diferentes'}), 400
    
    if not conta_pertence_ao_usuario(from_id, user_id):
        return jsonify({'error': 'Conta de origem não encontrada'}), 404
    
    if not conta_pertence_ao_usuario(to_id, user_id):
        return jsonify({'error': 'Conta de destino não encontrada'}), 404
    
    try:
        with db_transaction() as db:
            with db.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                # Debitar conta origem
                cursor.execute("UPDATE contas SET saldo = saldo - %s WHERE id = %s", (valor, from_id))
                
                # Creditar conta destino
                cursor.execute("UPDATE contas SET saldo = saldo + %s WHERE id = %s", (valor, to_id))
                
                # Obter nomes das contas
                cursor.execute("SELECT nome FROM contas WHERE id = %s", (from_id,))
                from_name = cursor.fetchone()['nome']
                
                cursor.execute("SELECT nome FROM contas WHERE id = %s", (to_id,))
                to_name = cursor.fetchone()['nome']
                
                # Registrar transações
                cursor.execute("""
                    INSERT INTO transacoes (conta_id, user_id, tipo, valor, descricao) 
                    VALUES (%s, %s, %s, %s, %s)
                """, (from_id, user_id, 'transfer_out', -valor, f"Para: {to_name} ({descricao})"))
                
                cursor.execute("""
                    INSERT INTO transacoes (conta_id, user_id, tipo, valor, descricao) 
                    VALUES (%s, %s, %s, %s, %s)
                """, (to_id, user_id, 'transfer_in', valor, f"De: {from_name} ({descricao})"))
        
        return jsonify({'message': 'Transferência realizada com sucesso!'})
    except Exception as e:
        return jsonify({'error': f'Erro ao realizar transferência: {str(e)}'}), 500

@app.route('/api/backup', methods=['GET'])
@login_required
def backup_dados():
    user_id = get_current_user_id()
    
    with get_db().cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
        cursor.execute("SELECT * FROM contas WHERE user_id = %s", (user_id,))
        contas = [dict(row) for row in cursor.fetchall()]
        
        cursor.execute("SELECT * FROM transacoes WHERE user_id = %s", (user_id,))
        transacoes = [dict(row) for row in cursor.fetchall()]
    
    backup_data = {
        'backupDate': datetime.now().isoformat(),
        'contas': contas,
        'transacoes': transacoes
    }
    
    return Response(
        json.dumps(backup_data, indent=2, default=str),
        mimetype='application/json',
        headers={'Content-Disposition': 'attachment;filename=backup_gestao.json'}
    )

@app.route('/api/relatorio', methods=['GET'])
@login_required
def get_relatorio():
    user_id = get_current_user_id()
    year = request.args.get('year', default=datetime.now().year, type=int)
    month = request.args.get('month', default=datetime.now().month, type=int)
    
    try:
        start_date = datetime(year, month, 1)
        end_date = (start_date + timedelta(days=32)).replace(day=1)
    except ValueError:
        return jsonify({'error': 'Data inválida'}), 400
    
    with get_db().cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
        cursor.execute("""
            SELECT t.*, c.nome as nome_conta, c.casa_de_aposta 
            FROM transacoes t 
            JOIN contas c ON t.conta_id = c.id 
            WHERE t.user_id = %s AND t.data_criacao >= %s AND t.data_criacao < %s
        """, (user_id, start_date, end_date))
        
        transacoes = [dict(row) for row in cursor.fetchall()]
    
    # Cálculos do relatório
    net_profit = sum(t['valor'] for t in transacoes if t['tipo'] in ['bet_placed', 'bet_won'])
    total_expenses = sum(t['valor'] for t in transacoes if t['tipo'] == 'expense')
    total_payments = sum(t['valor'] for t in transacoes if t['tipo'] == 'payment')

    analysis = {}
    for t in transacoes:
        if t['casa_de_aposta'] != 'pessoal':
            conta_id = t['conta_id']
            if conta_id not in analysis:
                analysis[conta_id] = {
                    'name': t['nome_conta'],
                    'profit': 0,
                    'wagered': 0,
                    'betCount': 0
                }
            
            if t['tipo'] in ['bet_placed', 'bet_won']:
                analysis[conta_id]['profit'] += t['valor']
            
            if t['tipo'] == 'bet_placed':
                details = t['detalhes'] or {}
                analysis[conta_id]['wagered'] += details.get('stake', 0)
                analysis[conta_id]['betCount'] += 1
    
    report_data = {
        'summary': {
            'netProfit': float(net_profit),
            'totalExpenses': float(abs(total_expenses)),
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
    
    if not conta_pertence_ao_usuario(conta_id, user_id):
        return jsonify({'error': 'Conta não encontrada'}), 404
    
    try:
        with db_transaction() as db:
            with db.cursor() as cursor:
                periodo_pago = datetime.now().strftime('%Y-%m')
                cursor.execute("""
                    UPDATE contas SET ultimo_periodo_pago = %s 
                    WHERE id = %s AND user_id = %s
                """, (periodo_pago, conta_id, user_id))
                
                if cursor.rowcount == 0:
                    return jsonify({'error': 'Conta não encontrada'}), 404
        
        return jsonify({'message': 'Pagamento registrado com sucesso!'})
    except Exception as e:
        return jsonify({'error': f'Erro ao registrar pagamento: {str(e)}'}), 500

@app.route('/api/restore', methods=['POST'])
@login_required
def restore_backup():
    user_id = get_current_user_id()
    
    if 'backupFile' not in request.files:
        return jsonify({'error': 'Nenhum arquivo enviado'}), 400
    
    file = request.files['backupFile']
    if file.filename == '':
        return jsonify({'error': 'Nenhum arquivo selecionado'}), 400
    
    if not file.filename.endswith('.json'):
        return jsonify({'error': 'Arquivo deve ser JSON'}), 400
    
    try:
        backup_data = json.load(file)
        contas = backup_data.get('contas', [])
        transacoes = backup_data.get('transacoes', [])
        
        if not contas and not transacoes:
            return jsonify({'error': 'Arquivo de backup vazio ou inválido'}), 400
        
        with db_transaction() as db:
            with db.cursor() as cursor:
                # Limpar dados atuais do usuário
                cursor.execute("DELETE FROM transacoes WHERE user_id = %s", (user_id,))
                cursor.execute("DELETE FROM contas WHERE user_id = %s", (user_id,))
                
                # Restaurar contas
                for conta in contas:
                    cursor.execute("""
                        INSERT INTO contas 
                        (id, user_id, nome, casa_de_aposta, saldo, saldo_freebets, meta, volume_clube, 
                         dia_pagamento, valor_pagamento, observacoes, ultimo_periodo_pago, ativa, data_ultimo_codigo)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        conta.get('id'), user_id, conta.get('nome'), conta.get('casa_de_aposta'),
                        conta.get('saldo'), conta.get('saldo_freebets'), conta.get('meta'),
                        conta.get('volume_clube'), conta.get('dia_pagamento'), conta.get('valor_pagamento'),
                        conta.get('observacoes'), conta.get('ultimo_periodo_pago'), 
                        conta.get('ativa', True), conta.get('data_ultimo_codigo')
                    ))
                
                # Restaurar transações
                for transacao in transacoes:
                    cursor.execute("""
                        INSERT INTO transacoes 
                        (id, conta_id, user_id, tipo, valor, descricao, detalhes, data_criacao)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        transacao.get('id'), transacao.get('conta_id'), user_id,
                        transacao.get('tipo'), transacao.get('valor'), transacao.get('descricao'),
                        json.dumps(transacao.get('detalhes')), transacao.get('data_criacao')
                    ))
        
        return jsonify({
            'message': f'{len(contas)} contas e {len(transacoes)} transações restauradas com sucesso!'
        })
    
    except json.JSONDecodeError:
        return jsonify({'error': 'Arquivo JSON inválido'}), 400
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
    
    if not file.filename.endswith('.csv'):
        return jsonify({'error': 'Arquivo deve ser CSV'}), 400
    
    try:
        stream = io.StringIO(file.stream.read().decode("UTF-8"), newline=None)
        csv_reader = csv.DictReader(stream)
        contas_para_processar = list(csv_reader)
        
        if not contas_para_processar:
            return jsonify({'error': 'CSV vazio ou inválido'}), 400
        
        criadas = 0
        atualizadas = 0
        
        with db_transaction() as db:
            with db.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                for conta_data in contas_para_processar:
                    nome = conta_data.get('nome', '').strip()
                    if not nome:
                        continue
                    
                    cursor.execute("SELECT id FROM contas WHERE nome = %s AND user_id = %s", (nome, user_id))
                    conta_existente = cursor.fetchone()
                    
                    dados = {
                        "nome": nome,
                        "casa_de_aposta": conta_data.get('casa_de_aposta') or None,
                        "saldo": float(conta_data.get('saldo') or 0),
                        "saldo_freebets": float(conta_data.get('saldo_freebets') or 0),
                        "dia_pagamento": int(conta_data.get('dia_pagamento')) if conta_data.get('dia_pagamento') else None,
                        "valor_pagamento": float(conta_data.get('valor_pagamento')) if conta_data.get('valor_pagamento') else None,
                        "observacoes": conta_data.get('observacoes') or None,
                        "data_ultimo_codigo": conta_data.get('data_ultimo_codigo') or None,
                    }
                    
                    if conta_existente:
                        cursor.execute("""
                            UPDATE contas SET 
                            casa_de_aposta=%s, saldo=%s, saldo_freebets=%s, dia_pagamento=%s, 
                            valor_pagamento=%s, observacoes=%s, data_ultimo_codigo=%s
                            WHERE id = %s AND user_id = %s
                        """, (
                            dados['casa_de_aposta'], dados['saldo'], dados['saldo_freebets'],
                            dados['dia_pagamento'], dados['valor_pagamento'], dados['observacoes'],
                            dados['data_ultimo_codigo'], conta_existente['id'], user_id
                        ))
                        atualizadas += 1
                    else:
                        cursor.execute("""
                            INSERT INTO contas 
                            (user_id, nome, casa_de_aposta, saldo, saldo_freebets, dia_pagamento, 
                             valor_pagamento, observacoes, data_ultimo_codigo)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """, (
                            user_id, dados['nome'], dados['casa_de_aposta'], dados['saldo'],
                            dados['saldo_freebets'], dados['dia_pagamento'], dados['valor_pagamento'],
                            dados['observacoes'], dados['data_ultimo_codigo']
                        ))
                        criadas += 1
        
        return jsonify({
            'message': f'{criadas} contas criadas e {atualizadas} atualizadas com sucesso!'
        })
    
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

# --- Handlers de Erro ---
@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Recurso não encontrado'}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Erro interno do servidor'}), 500

@app.errorhandler(psycopg2.Error)
def handle_db_error(error):
    return jsonify({'error': 'Erro no banco de dados'}), 500

if __name__ == '__main__':
    app.run(debug=True)
