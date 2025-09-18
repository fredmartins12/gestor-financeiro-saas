-- Apaga as tabelas se elas já existirem para garantir um início limpo
DROP TABLE IF EXISTS transacoes;
DROP TABLE IF EXISTS contas;
DROP TABLE IF EXISTS usuarios;

-- Tabela para armazenar os usuários do sistema
CREATE TABLE usuarios (
    id INTEGER PRIMARY KEY, -- Em SQLite, INTEGER PRIMARY KEY já é autoincrementável
    email TEXT UNIQUE NOT NULL,
    senha_hash TEXT NOT NULL,
    data_criacao DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Tabela para as contas (de apostas ou pessoais)
CREATE TABLE contas (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL,
    nome TEXT NOT NULL,
    casa_de_aposta TEXT,
    saldo REAL DEFAULT 0.00,
    saldo_freebets REAL DEFAULT 0.00,
    meta REAL DEFAULT 100.00,
    volume_clube REAL DEFAULT 0.00,
    dia_pagamento INTEGER,
    valor_pagamento REAL,
    observacoes TEXT,
    ultimo_periodo_pago TEXT, -- Armazena o período pago, ex: "2025-09"
    ativa INTEGER DEFAULT 1, -- Usamos 1 para TRUE (verdadeiro) e 0 para FALSE (falso)
    data_ultimo_codigo DATE, -- Para armazenar a data do último código
    FOREIGN KEY (user_id) REFERENCES usuarios(id) ON DELETE CASCADE
);

-- Tabela para o histórico de transações
CREATE TABLE transacoes (
    id INTEGER PRIMARY KEY,
    conta_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    tipo TEXT NOT NULL,
    valor REAL NOT NULL,
    descricao TEXT,
    -- 'detalhes' armazena dados extras da transação como um JSON em formato de texto
    detalhes TEXT,
    data_criacao DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (conta_id) REFERENCES contas(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES usuarios(id) ON DELETE CASCADE
);