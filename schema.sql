-- Apaga as tabelas se elas já existirem para garantir um início limpo
DROP TABLE IF EXISTS transacoes;
DROP TABLE IF EXISTS contas;
DROP TABLE IF EXISTS usuarios;

-- Tabela para armazenar os usuários do sistema
CREATE TABLE usuarios (
    id SERIAL PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    senha_hash TEXT NOT NULL,
    data_criacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tabela para as contas (de apostas ou pessoais)
CREATE TABLE contas (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    nome TEXT NOT NULL,
    casa_de_aposta TEXT,
    saldo NUMERIC DEFAULT 0.00,
    saldo_freebets NUMERIC DEFAULT 0.00,
    meta NUMERIC DEFAULT 100.00,
    volume_clube NUMERIC DEFAULT 0.00,
    dia_pagamento INTEGER,
    valor_pagamento NUMERIC,
    observacoes TEXT,
    ultimo_periodo_pago TEXT,
    ativa BOOLEAN DEFAULT TRUE,
    data_ultimo_codigo DATE
);

-- Tabela para o histórico de transações
CREATE TABLE transacoes (
    id SERIAL PRIMARY KEY,
    conta_id INTEGER NOT NULL REFERENCES contas(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    tipo TEXT NOT NULL,
    valor NUMERIC NOT NULL,
    descricao TEXT,
    detalhes JSON,
    data_criacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
