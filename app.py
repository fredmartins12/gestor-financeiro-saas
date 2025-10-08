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
# Certifique-se de definir esta variável de ambiente no seu provedor (Render)
DATABASE_URL = os.environ.get('DATABASE_URL') 

# --- Configuração do Flask-Login ---
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# --- Context Manager para Transações (Garante Atomicidade) ---
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
    
    # --- CORREÇÃO APLICADA AQUI: Tratar o caso de resumo vazio (tabela transacoes vazia para novo usuário) ---
    if resumo is None or resumo['entradas'] is None:
        resumo = {'entradas': 0, 'saidas': 0, 'lucro_prejuizo': 0}

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
    
    # Prevenção simples contra injeção de SQL ou acesso não autorizado, embora o ORM do psycopg2 já ajude
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
                    data.get('diaPagamento'), data.get('valorPagamento'), 
                    data.get('observacoes'), data.get('ultimoPeriodoPago'), 
                    data.get('dataUltimoCodigo'), conta_id, user_id
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
                # Apenas desativa a conta, mantendo o registro no histórico
                cursor.execute("UPDATE contas SET ativa = FALSE WHERE id = %s AND user_id = %s", (conta_id, user_id))
                if cursor.rowcount == 0:
                    return jsonify({'error': 'Conta não encontrada'}), 404
        return jsonify({'message': 'Conta desativada com sucesso'})
    except Exception as e:
        return jsonify({'error': f'Erro ao desativar conta: {str(e)}'}), 500

@app.route('/api/transacoes/generico', methods=['POST'])
@login_required
@validar_json_campos(['conta_id', 'tipo', 'valor', 'descricao'])
def add_transacao_generica():
    user_id = get_current_user_id()
    data = request.get_json()
    conta_id = data['conta_id']
    tipo = data['tipo'] # 'deposit', 'withdrawal', 'expense'
    valor = float(data['valor'])
    descricao = data['descricao']

    if not conta_pertence_ao_usuario(conta_id, user_id):
        return jsonify({'error': 'Conta não encontrada'}), 404

    # Determinar a modificação do saldo. Deposit > 0, Withdrawal/Expense < 0
    if tipo == 'deposit':
        valor_ajustado = abs(valor)
    elif tipo in ['withdrawal', 'expense']:
        valor_ajustado = -abs(valor)
    else:
        return jsonify({'error': 'Tipo de transação inválido.'}), 400

    try:
        with db_transaction() as db:
            with db.cursor() as cursor:
                # 1. Inserir a Transação
                cursor.execute("""
                    INSERT INTO transacoes (user_id, conta_id, tipo, valor, descricao, detalhes) 
                    VALUES (%s, %s, %s, %s, %s, %s) 
                    RETURNING id
                """, (user_id, conta_id, tipo, valor_ajustado, descricao, json.dumps({'origem': tipo})))
                
                # 2. Atualizar o Saldo da Conta
                cursor.execute("""
                    UPDATE contas 
                    SET saldo = saldo + %s 
                    WHERE id = %s AND user_id = %s
                """, (valor_ajustado, conta_id, user_id))

        return jsonify({'message': f'{tipo.capitalize()} de {valor_ajustado:.2f} registrado com sucesso.'}), 201
    except Exception as e:
        return jsonify({'error': f'Erro ao registrar transação: {str(e)}'}), 500

@app.route('/api/transferencia', methods=['POST'])
@login_required
@validar_json_campos(['conta_origem_id', 'conta_destino_id', 'valor', 'descricao'])
def transferencia():
    user_id = get_current_user_id()
    data = request.get_json()
    origem_id = data['conta_origem_id']
    destino_id = data['conta_destino_id']
    valor = float(data['valor'])
    descricao = data['descricao']

    if origem_id == destino_id:
        return jsonify({'error': 'Conta de origem e destino devem ser diferentes.'}), 400
    if valor <= 0:
        return jsonify({'error': 'Valor deve ser positivo.'}), 400
    if not (conta_pertence_ao_usuario(origem_id, user_id) and conta_pertence_ao_usuario(destino_id, user_id)):
        return jsonify({'error': 'Uma ou ambas as contas não foram encontradas.'}), 404

    try:
        with db_transaction() as db:
            with db.cursor() as cursor:
                # 1. Débito da Conta de Origem
                cursor.execute("SELECT saldo FROM contas WHERE id = %s AND user_id = %s", (origem_id, user_id))
                saldo_origem = cursor.fetchone()[0]
                if saldo_origem < valor:
                    raise Exception('Saldo insuficiente na conta de origem.')

                cursor.execute("UPDATE contas SET saldo = saldo - %s WHERE id = %s", (valor, origem_id))
                
                # 2. Crédito na Conta de Destino
                cursor.execute("UPDATE contas SET saldo = saldo + %s WHERE id = %s", (valor, destino_id))
                
                # 3. Registrar Transações (Débito)
                detalhes_origem = json.dumps({'tipo': 'transfer_out', 'destino_id': destino_id})
                cursor.execute("""
                    INSERT INTO transacoes (user_id, conta_id, tipo, valor, descricao, detalhes) 
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (user_id, origem_id, 'transfer', -valor, f'Transferência para: {descricao}', detalhes_origem))

                # 4. Registrar Transações (Crédito)
                detalhes_destino = json.dumps({'tipo': 'transfer_in', 'origem_id': origem_id})
                cursor.execute("""
                    INSERT INTO transacoes (user_id, conta_id, tipo, valor, descricao, detalhes) 
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (user_id, destino_id, 'transfer', valor, f'Transferência de: {descricao}', detalhes_destino))

        return jsonify({'message': 'Transferência realizada com sucesso.'}), 201
    except Exception as e:
        return jsonify({'error': f'Erro ao realizar transferência: {str(e)}'}), 500

@app.route('/api/contas/<int:conta_id>/pagamento', methods=['POST'])
@login_required
def registrar_pagamento_clube(conta_id):
    user_id = get_current_user_id()
    
    if not conta_pertence_ao_usuario(conta_id, user_id):
        return jsonify({'error': 'Conta não encontrada'}), 404

    try:
        with db_transaction() as db:
            with db.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                # 1. Obter valor do pagamento e dia
                cursor.execute("SELECT valor_pagamento, dia_pagamento FROM contas WHERE id = %s AND user_id = %s", (conta_id, user_id))
                conta = cursor.fetchone()
                if not conta or not conta['valor_pagamento'] or not conta['dia_pagamento']:
                    return jsonify({'error': 'Configuração de pagamento da conta inválida.'}), 400
                
                valor_pagamento = conta['valor_pagamento']
                
                # 2. Registrar Transação de Débito (expense/club_payment)
                hoje = datetime.now()
                periodo_pago = f'{hoje.year}-{str(hoje.month).zfill(2)}'

                cursor.execute("""
                    INSERT INTO transacoes (user_id, conta_id, tipo, valor, descricao, detalhes) 
                    VALUES (%s, %s, %s, %s, %s, %s) 
                """, (
                    user_id, conta_id, 'club_payment', -valor_pagamento, 
                    f'Pagamento do Clube - Período {periodo_pago}', 
                    json.dumps({'periodo': periodo_pago})
                ))

                # 3. Atualizar o saldo da conta
                cursor.execute("""
                    UPDATE contas 
                    SET saldo = saldo - %s, ultimo_periodo_pago = %s 
                    WHERE id = %s AND user_id = %s
                """, (valor_pagamento, periodo_pago, conta_id, user_id))
        
        return jsonify({'message': 'Pagamento do clube registrado com sucesso.'}), 201
    except Exception as e:
        return jsonify({'error': f'Erro ao registrar pagamento: {str(e)}'}), 500


@app.route('/api/operacoes', methods=['POST'])
@login_required
@validar_json_campos(['conta_id', 'tipo', 'valor', 'descricao', 'detalhes'])
def add_operacao():
    user_id = get_current_user_id()
    data = request.get_json()
    conta_id = data['conta_id']
    tipo = data['tipo'] # 'bet_placed' ou 'freebet_placed'
    valor = float(data['valor'])
    descricao = data['descricao']
    detalhes = data['detalhes'] # Deve ser um objeto JSON stringificado

    if not conta_pertence_ao_usuario(conta_id, user_id):
        return jsonify({'error': 'Conta não encontrada'}), 404
    if valor <= 0:
        return jsonify({'error': 'Valor deve ser positivo.'}), 400
    if tipo not in ['bet_placed', 'freebet_placed']:
        return jsonify({'error': 'Tipo de operação inválido.'}), 400
        
    valor_ajustado = -abs(valor) # Sempre um débito

    try:
        with db_transaction() as db:
            with db.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                # 1. Verificar e atualizar saldos
                if tipo == 'bet_placed':
                    cursor.execute("SELECT saldo FROM contas WHERE id = %s AND user_id = %s", (conta_id, user_id))
                    saldo_atual = cursor.fetchone()['saldo']
                    if saldo_atual < valor:
                         raise Exception('Saldo insuficiente na conta para esta aposta.')
                    # Debita do saldo
                    cursor.execute("UPDATE contas SET saldo = saldo + %s WHERE id = %s", (valor_ajustado, conta_id))
                else: # freebet_placed
                    cursor.execute("SELECT saldo_freebets FROM contas WHERE id = %s AND user_id = %s", (conta_id, user_id))
                    saldo_fb = cursor.fetchone()['saldo_freebets']
                    if saldo_fb < valor:
                        raise Exception('Saldo de Freebet insuficiente na conta.')
                    # Debita do saldo de freebet
                    cursor.execute("UPDATE contas SET saldo_freebets = saldo_freebets + %s WHERE id = %s", (valor_ajustado, conta_id))

                # 2. Registrar Transação
                cursor.execute("""
                    INSERT INTO transacoes (user_id, conta_id, tipo, valor, descricao, detalhes) 
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (user_id, conta_id, tipo, valor_ajustado, descricao, json.dumps(detalhes)))
                
        return jsonify({'message': f'{tipo.replace("_", " ").capitalize()} registrada com sucesso.'}), 201
    except Exception as e:
        # A exceção pode vir da verificação de saldo ou do banco de dados
        return jsonify({'error': f'Erro ao registrar operação: {str(e)}'}), 500

@app.route('/api/operacoes/resolver', methods=['POST'])
@login_required
@validar_json_campos(['operationId', 'status', 'ganho_total'])
def resolve_operacao():
    user_id = get_current_user_id()
    data = request.get_json()
    operation_id = data['operationId']
    status = data['status'] # 'ganha' ou 'perdida'
    ganho_total = float(data['ganho_total'])

    if status not in ['ganha', 'perdida']:
        return jsonify({'error': 'Status de resolução inválido.'}), 400
    if status == 'ganha' and ganho_total <= 0:
         return jsonify({'error': 'Ganho total deve ser positivo para operação ganha.'}), 400
    if status == 'perdida' and ganho_total != 0:
        return jsonify({'error': 'Ganho total deve ser zero para operação perdida.'}), 400

    try:
        with db_transaction() as db:
            with db.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                # 1. Recuperar todas as transações (apostas) vinculadas à operationId
                cursor.execute("""
                    SELECT * FROM transacoes 
                    WHERE user_id = %s 
                    AND tipo IN ('bet_placed', 'freebet_placed') 
                    AND detalhes->>'operationId' = %s
                    AND detalhes->>'status' = 'ativa'
                """, (user_id, operation_id))
                apostas = cursor.fetchall()

                if not apostas:
                    return jsonify({'error': 'Nenhuma operação ativa encontrada com este ID.'}), 404
                
                # 2. Processar cada aposta na operação
                for aposta in apostas:
                    aposta_id = aposta['id']
                    conta_id = aposta['conta_id']
                    valor_apostado = abs(aposta['valor'])
                    tipo_aposta = aposta['tipo'] # bet_placed ou freebet_placed

                    if status == 'ganha':
                        # Se for aposta normal, o ganho total deve ser creditado ao saldo.
                        # Se for freebet, o ganho líquido (ganho_total - valor_apostado) deve ser creditado ao saldo.
                        if tipo_aposta == 'freebet_placed':
                            valor_credito = ganho_total - valor_apostado
                            descricao = f"Ganho Freebet - Op {operation_id} (Líquido: {valor_credito:.2f})"
                        else:
                            valor_credito = ganho_total
                            descricao = f"Ganho Aposta - Op {operation_id}"
                        
                        # 3. Registrar Transação de Ganho (bet_won)
                        cursor.execute("""
                            INSERT INTO transacoes (user_id, conta_id, tipo, valor, descricao, detalhes) 
                            VALUES (%s, %s, %s, %s, %s, %s)
                        """, (user_id, conta_id, 'bet_won', valor_credito, descricao, json.dumps({'operationId': operation_id, 'status': status, 'aposta_id': aposta_id})))
                        
                        # 4. Atualizar Saldo da Conta
                        cursor.execute("""
                            UPDATE contas 
                            SET saldo = saldo + %s 
                            WHERE id = %s
                        """, (valor_credito, conta_id))

                    # 5. Marcar Aposta Original como resolvida
                    novos_detalhes = aposta['detalhes']
                    novos_detalhes['status'] = status
                    novos_detalhes['resultado'] = ganho_total

                    cursor.execute("""
                        UPDATE transacoes 
                        SET detalhes = %s
                        WHERE id = %s
                    """, (json.dumps(novos_detalhes), aposta_id))

        return jsonify({'message': f'Operação {operation_id} resolvida como {status}.'}), 200
    except Exception as e:
        return jsonify({'error': f'Erro ao resolver operação: {str(e)}'}), 500

@app.route('/api/relatorio', methods=['GET'])
@login_required
def get_relatorio():
    user_id = get_current_user_id()
    
    with get_db().cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
        # 1. Resumo por Conta (Saldo, Freebet, P/L, Volume)
        cursor.execute("""
            SELECT 
                c.id, c.nome, c.saldo, c.saldo_freebets, c.meta, c.volume_clube, 
                COALESCE(SUM(CASE WHEN t.tipo IN ('bet_placed', 'bet_won') THEN t.valor ELSE 0 END), 0) AS pl_total,
                COALESCE(SUM(CASE WHEN t.tipo = 'bet_placed' THEN ABS(t.valor) ELSE 0 END), 0) AS volume_apostado
            FROM contas c
            LEFT JOIN transacoes t ON c.id = t.conta_id AND t.user_id = %s
            WHERE c.user_id = %s AND c.ativa = TRUE
            GROUP BY c.id, c.nome, c.saldo, c.saldo_freebets, c.meta, c.volume_clube
            ORDER BY c.nome
        """, (user_id, user_id))
        resumo_contas = [dict(row) for row in cursor.fetchall()]

        # 2. Resumo Mensal de Ganhos/Perdas/Despesas/Pagamentos
        # Define 12 meses (do mês atual até 11 meses atrás)
        hoje = datetime.now()
        datas_consulta = [(hoje.replace(day=1) - timedelta(days=30*i)).replace(day=1) for i in range(12)]
        datas_consulta = sorted(list(set(d for d in datas_consulta if d.month <= hoje.month or d.year < hoje.year))) # Unique and sorted

        resumo_mensal = []
        for start_date in datas_consulta:
            end_date = (start_date + timedelta(days=32)).replace(day=1) # Próximo primeiro dia do mês
            periodo = f'{start_date.year}-{str(start_date.month).zfill(2)}'

            cursor.execute("""
                SELECT 
                    COALESCE(SUM(CASE WHEN t.tipo IN ('bet_placed', 'bet_won') THEN t.valor ELSE 0 END), 0) AS pl_mes,
                    COALESCE(SUM(CASE WHEN t.tipo = 'expense' THEN ABS(t.valor) ELSE 0 END), 0) AS despesas_mes,
                    COALESCE(SUM(CASE WHEN t.tipo = 'club_payment' THEN ABS(t.valor) ELSE 0 END), 0) AS pagamentos_mes
                FROM transacoes t
                WHERE t.user_id = %s
                AND t.data_criacao >= %s
                AND t.data_criacao < %s
            """, (user_id, start_date, end_date))
            
            resumo = cursor.fetchone()
            if resumo:
                resumo_mensal.append({
                    'periodo': periodo,
                    'pl_mes': float(resumo['pl_mes']),
                    'despesas_mes': float(resumo['despesas_mes']),
                    'pagamentos_mes': float(resumo['pagamentos_mes']),
                })

    return jsonify({
        'resumoContas': resumo_contas,
        'resumoMensal': resumo_mensal
    })

# --- Rotas de Gerenciamento de Dados ---
@app.route('/api/backup', methods=['GET'])
@login_required
def backup_data():
    user_id = get_current_user_id()
    data = {}
    
    with get_db().cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
        # Exportar contas
        cursor.execute("SELECT * FROM contas WHERE user_id = %s", (user_id,))
        data['contas'] = [dict(row) for row in cursor.fetchall()]
        
        # Exportar transações
        cursor.execute("SELECT * FROM transacoes WHERE user_id = %s", (user_id,))
        data['transacoes'] = [dict(row) for row in cursor.fetchall()]

    # Tratar datas e objetos JSON para serialização
    def default_serializer(obj):
        if isinstance(obj, (datetime, timedelta)):
            return obj.isoformat()
        if isinstance(obj, dict) and 'detalhes' in obj and isinstance(obj['detalhes'], str):
             # Transacoes vêm como DictCursor. O campo 'detalhes' pode precisar de parse, mas o padrão é string
             try:
                 obj['detalhes'] = json.loads(obj['detalhes'])
             except:
                 pass
        return obj

    response_data = json.dumps(data, indent=4, default=default_serializer)
    
    return Response(
        response_data,
        mimetype="application/json",
        headers={"Content-disposition": "attachment; filename=backup_gestao_bets.json"}
    )

@app.route('/api/restore', methods=['POST'])
@login_required
def restore_data():
    user_id = get_current_user_id()

    if 'backupFile' not in request.files:
        return jsonify({'error': 'Nenhum arquivo de backup enviado.'}), 400

    file = request.files['backupFile']
    if file.filename == '' or not file.filename.endswith('.json'):
        return jsonify({'error': 'Arquivo inválido. Por favor, envie um arquivo .json.'}), 400

    try:
        data = json.load(file)
        if 'contas' not in data or 'transacoes' not in data:
            return jsonify({'error': 'Formato de arquivo de backup inválido.'}), 400
        
        with db_transaction() as db:
            with db.cursor() as cursor:
                # 1. Limpar dados existentes do usuário
                cursor.execute("DELETE FROM transacoes WHERE user_id = %s", (user_id,))
                cursor.execute("DELETE FROM contas WHERE user_id = %s", (user_id,))
                
                # 2. Inserir novas contas
                for conta in data['contas']:
                    # Remove campos desnecessários ou que podem causar conflito de tipo
                    conta.pop('user_id', None)
                    conta.pop('id', None)
                    
                    cursor.execute("""
                        INSERT INTO contas 
                        (user_id, nome, casa_de_aposta, saldo, saldo_freebets, meta, volume_clube, dia_pagamento, valor_pagamento, observacoes, data_ultimo_codigo, ultimo_periodo_pago, ativa)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        user_id, conta.get('nome'), conta.get('casa_de_aposta'), conta.get('saldo'), 
                        conta.get('saldo_freebets'), conta.get('meta'), conta.get('volume_clube'), 
                        conta.get('dia_pagamento'), conta.get('valor_pagamento'), conta.get('observacoes'), 
                        conta.get('data_ultimo_codigo'), conta.get('ultimo_periodo_pago'), conta.get('ativa', True)
                    ))

                # 3. Inserir novas transações
                for transacao in data['transacoes']:
                    # Remove campos desnecessários
                    transacao.pop('user_id', None)
                    transacao.pop('id', None)
                    
                    # Garantir que detalhes seja uma string JSON válida
                    detalhes_str = transacao.get('detalhes')
                    if isinstance(detalhes_str, dict):
                        detalhes_str = json.dumps(detalhes_str)
                    
                    cursor.execute("""
                        INSERT INTO transacoes
                        (user_id, conta_id, tipo, valor, descricao, data_criacao, detalhes)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """, (
                        user_id, transacao.get('conta_id'), transacao.get('tipo'), transacao.get('valor'), 
                        transacao.get('descricao'), transacao.get('data_criacao'), detalhes_str
                    ))
        
        return jsonify({'message': 'Dados restaurados com sucesso!'}), 200
    except json.JSONDecodeError:
        return jsonify({'error': 'O arquivo de backup não é um JSON válido.'}), 400
    except Exception as e:
        return jsonify({'error': f'Erro ao restaurar dados: {str(e)}'}), 500

@app.route('/api/import-csv', methods=['POST'])
@login_required
def import_csv():
    user_id = get_current_user_id()

    if 'csvFile' not in request.files:
        return jsonify({'error': 'Nenhum arquivo CSV enviado.'}), 400

    file = request.files['csvFile']
    if file.filename == '' or not file.filename.endswith('.csv'):
        return jsonify({'error': 'Arquivo inválido. Por favor, envie um arquivo .csv.'}), 400

    stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
    reader = csv.DictReader(stream, delimiter=',')
    
    atualizadas = 0
    criadas = 0

    try:
        with db_transaction() as db:
            with db.cursor() as cursor:
                for row in reader:
                    dados = {k.strip(): v.strip() if v else None for k, v in row.items()}
                    nome_conta = dados.get('nome')
                    
                    if not nome_conta:
                        continue # Pula linhas sem nome
                    
                    # Tenta encontrar conta existente para atualização
                    cursor.execute("SELECT id FROM contas WHERE user_id = %s AND nome = %s", (user_id, nome_conta))
                    conta_existente = cursor.fetchone()

                    # Prepara dados (conversão de tipo)
                    saldo = float(dados.get('saldo', 0) or 0)
                    saldo_freebets = float(dados.get('saldo_freebets', 0) or 0)
                    dia_pagamento = int(dados.get('dia_pagamento')) if dados.get('dia_pagamento') else None
                    valor_pagamento = float(dados.get('valor_pagamento', 0) or 0)
                    
                    # Se a conta existe, atualiza
                    if conta_existente:
                        conta_id = conta_existente[0]
                        cursor.execute("""
                            UPDATE contas SET 
                            casa_de_aposta=%s, saldo=%s, saldo_freebets=%s, 
                            dia_pagamento=%s, valor_pagamento=%s, observacoes=%s, 
                            data_ultimo_codigo=%s 
                            WHERE id = %s
                        """, (
                            dados.get('casa_de_aposta'), saldo, saldo_freebets, 
                            dia_pagamento, valor_pagamento, 
                            dados.get('observacoes'), dados.get('data_ultimo_codigo'), conta_id
                        ))
                        atualizadas += 1
                    # Se a conta não existe, cria
                    else:
                        cursor.execute("""
                            INSERT INTO contas 
                            (user_id, nome, casa_de_aposta, saldo, saldo_freebets, dia_pagamento, valor_pagamento, observacoes, data_ultimo_codigo)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """, (
                            user_id, dados['nome'], dados['casa_de_aposta'], saldo,
                            saldo_freebets, dia_pagamento, valor_pagamento,
                            dados['observacoes'], dados['data_ultimo_codigo']
                        ))
                        criadas += 1
        
        return jsonify({
            'message': f'{criadas} contas criadas e {atualizadas} atualizadas com sucesso!'
        }), 200
    
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
    # Loga o erro, mas retorna uma mensagem segura para o frontend
    return jsonify({'error': 'Erro interno do servidor. Consulte os logs.'}), 500

@app.errorhandler(psycopg2.Error)
def handle_db_error(e):
    return jsonify({'error': f'Erro de banco de dados: {e.pgerror}'}), 500

if __name__ == '__main__':
    # Configurar esta porta para o Render
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
