-- =====================================================================
-- VemSUS — Banco de dados SQLite
-- Versão SQLite do modelo v2 (originalmente escrito para PostgreSQL).
--
-- Compatível com o backend (backend/app/db.py): as tabelas `units`, `geocode_cache`
-- e `sync_log` têm EXATAMENTE as mesmas colunas, na mesma ordem. O backend grava
-- com INSERT posicional, então NÃO acrescente nem reordene colunas dessas tabelas.
--
-- Fonte dos dados: CKAN dados.recife.pe.gov.br, resource c960077b-640c-4cbc-9fac-01be82bf54d9
--   "Rede de atenção à saúde no Recife" (ODbL) — uma linha por unidade x serviço.
-- Pipeline: CKAN -> [backend: agrupa por CNES, valida coordenadas, geocodifica] -> units
--
-- Princípios do produto: sem login, sem cadastro, sem dado pessoal.
-- Tema, acessibilidade, modo infantil e localização do usuário ficam no NAVEGADOR.
--
-- Uso:  sqlite3 backend/data/vemsus.db < database/vemsus_schema_sqlite.sql
-- O script é idempotente: pode ser executado mais de uma vez sem erro.
-- Requer SQLite 3.38+ (funções JSON embutidas).
-- =====================================================================

PRAGMA foreign_keys = ON;   -- vale só para a conexão que executa o script

-- ---------------------------------------------------------------------
-- 1. DOMÍNIOS (lookups)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS fonte_dados (
    codigo     TEXT PRIMARY KEY,                 -- 'official'
    descricao  TEXT NOT NULL,
    url        TEXT,
    licenca    TEXT
);

CREATE TABLE IF NOT EXISTS tipo_unidade (
    codigo         TEXT PRIMARY KEY,             -- igual ao UnitType do app
    nome_completo  TEXT NOT NULL,
    porta_entrada  INTEGER NOT NULL DEFAULT 0 CHECK (porta_entrada IN (0,1)),
    cor_marcador   TEXT NOT NULL CHECK (cor_marcador IN ('verde','vermelho')),
    ordem          INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS servico (             -- ServiceTag do app
    codigo            TEXT PRIMARY KEY,          -- slug: 'saude-bucal'
    nome              TEXT NOT NULL UNIQUE,      -- rótulo exibido: 'Saúde Bucal'
    emoji             TEXT,
    categoria_rapida  INTEGER NOT NULL DEFAULT 0 CHECK (categoria_rapida IN (0,1)),  -- card da tela inicial
    filtro_infantil   INTEGER NOT NULL DEFAULT 0 CHECK (filtro_infantil  IN (0,1)),  -- priorizado no Modo Infantil
    ordem             INTEGER NOT NULL DEFAULT 0
);

-- Dicionário popular -> serviço (backend/app/synonyms.py). Termos sem acento e em minúsculas.
CREATE TABLE IF NOT EXISTS sinonimo_busca (
    termo           TEXT NOT NULL CHECK (termo = lower(trim(termo))),
    servico_codigo  TEXT NOT NULL REFERENCES servico(codigo) ON DELETE CASCADE,
    PRIMARY KEY (termo, servico_codigo)
);

-- ---------------------------------------------------------------------
-- 2. UNIDADES, CACHE E LOG — tabelas usadas pelo backend (idênticas a db.py)
--    Restrições (CHECK/REFERENCES) não alteram colunas; só garantem a consistência.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS units (
  id TEXT PRIMARY KEY,                           -- 'cnes-2400001' ou hash de nome+endereço (estável entre cargas)
  cnes TEXT,
  name TEXT NOT NULL,
  type TEXT NOT NULL REFERENCES tipo_unidade(codigo),
  address TEXT NOT NULL,                         -- vazio na origem -> 'Informação não disponível na base oficial.'
  neighborhood TEXT,
  phone TEXT,
  schedule TEXT,                                 -- horários distintos unidos por ' · '
  lat REAL,
  lng REAL,
  geo_source TEXT NOT NULL,                      -- official | geocoded (aproximada) | missing
  services TEXT NOT NULL,                        -- lista JSON de nomes de serviço (ServiceTag)
  before_visit TEXT,                             -- coluna "como_usar" do portal (orientações oficiais)
  updated_at TEXT NOT NULL,
  -- Nunca se inventa coordenada: 'missing' <=> sem lat/lng; a unidade não é exposta no mapa.
  CHECK (geo_source IN ('official','geocoded','missing')),
  CHECK ((geo_source = 'missing' AND lat IS NULL AND lng IS NULL)
      OR (geo_source <> 'missing' AND lat IS NOT NULL AND lng IS NOT NULL)),
  -- Caixa do Recife + margem (igual a geo_min/max_* em backend/app/config.py; ajuste os dois juntos)
  CHECK (lat IS NULL OR lat BETWEEN -8.25 AND -7.85),
  CHECK (lng IS NULL OR lng BETWEEN -35.10 AND -34.80),
  CHECK (json_valid(services) AND json_type(services) = 'array')
);
CREATE INDEX IF NOT EXISTS idx_units_type ON units(type);
CREATE INDEX IF NOT EXISTS idx_units_cnes ON units(cnes);

-- Cache do Nominatim. lat/lng NULL = "não encontrado" (falha conhecida, retentada depois).
CREATE TABLE IF NOT EXISTS geocode_cache (
  key TEXT PRIMARY KEY,                          -- 'endereço|bairro' em minúsculas
  lat REAL,
  lng REAL,
  fetched_at REAL NOT NULL,                      -- epoch (segundos)
  CHECK ((lat IS NULL) = (lng IS NULL))
);

-- Histórico de cada sincronização com o portal (usado por /api/meta e /api/admin/diagnostico).
CREATE TABLE IF NOT EXISTS sync_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  ok INTEGER,
  units_saved INTEGER,
  without_geo INTEGER,
  error TEXT,
  diagnostics TEXT                               -- JSON: tipos não reconhecidos, coordenadas corrigidas/inválidas...
);

-- ---------------------------------------------------------------------
-- 3. TABELAS DO MODELO v2 AINDA NÃO USADAS PELO BACKEND
-- ---------------------------------------------------------------------
-- Staging: linhas EXATAS do CKAN da última sincronização (truncar a cada rodada).
-- Latitude/longitude ficam como texto: o portal traz "-8,0476", sinais trocados etc.
CREATE TABLE IF NOT EXISTS ckan_registro_bruto (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    sync_id            INTEGER NOT NULL REFERENCES sync_log(id) ON DELETE CASCADE,
    ckan_id            INTEGER,                   -- _id do datastore
    tipo_unidade       TEXT,
    nome_oficial       TEXT,
    rpa                REAL,
    distrito_sanitario REAL,
    microregiao        REAL,
    cnes               TEXT,
    cod_nat            TEXT,
    tipo_servico       TEXT,
    endereco           TEXT,                      -- coluna "endereço" no portal
    bairro             TEXT,
    fone               TEXT,
    especialidade      TEXT,
    como_usar          TEXT,
    horario            TEXT,
    ordem              TEXT,
    latitude_txt       TEXT,
    longitude_txt      TEXT
);
CREATE INDEX IF NOT EXISTS idx_bruto_cnes ON ckan_registro_bruto(cnes);

-- Conteúdo (SAMU 192, Sobre/Privacidade, textos)
CREATE TABLE IF NOT EXISTS emergencia_contato (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    nome       TEXT NOT NULL,
    numero     TEXT NOT NULL,                     -- '192' (link tel:)
    descricao  TEXT,
    ativo      INTEGER NOT NULL DEFAULT 1 CHECK (ativo IN (0,1))
);
CREATE TABLE IF NOT EXISTS emergencia_situacao (  -- acordeão "Quando ligar?"
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    contato_id  INTEGER NOT NULL REFERENCES emergencia_contato(id) ON DELETE CASCADE,
    titulo      TEXT NOT NULL,
    descricao   TEXT,
    ordem       INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS pagina_institucional (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    slug           TEXT NOT NULL UNIQUE CHECK (slug IN ('about','privacy','how-it-works')),
    titulo         TEXT NOT NULL,
    conteudo_md    TEXT NOT NULL,
    atualizado_em  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);
CREATE TABLE IF NOT EXISTS texto_interface (
    chave           TEXT PRIMARY KEY,
    texto           TEXT NOT NULL,
    texto_infantil  TEXT                           -- linguagem simplificada (Modo Infantil)
);

-- Métrica anônima (OPCIONAL) — sem IP, sem localização, sem identificador.
CREATE TABLE IF NOT EXISTS evento_busca (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    ocorrido_em      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    termo            TEXT CHECK (length(termo) <= 100),
    servico_codigo   TEXT REFERENCES servico(codigo),
    tipo_codigo      TEXT REFERENCES tipo_unidade(codigo),
    modo_infantil    INTEGER NOT NULL DEFAULT 0 CHECK (modo_infantil IN (0,1)),    -- só a flag
    usou_localizacao INTEGER NOT NULL DEFAULT 0 CHECK (usou_localizacao IN (0,1)), -- nunca o valor
    qtd_resultados   INTEGER
);

-- ---------------------------------------------------------------------
-- 4. VIEWS
-- ---------------------------------------------------------------------
DROP VIEW IF EXISTS v_unidade_servico;
DROP VIEW IF EXISTS v_unidade;
DROP VIEW IF EXISTS v_meta;
DROP VIEW IF EXISTS v_qualidade;

-- Relação unidade x serviço "desdobrada" a partir da lista JSON de units.services
CREATE VIEW v_unidade_servico AS
SELECT u.id AS unidade_id, s.codigo AS servico_codigo, j.value AS servico_nome
FROM units u, json_each(u.services) AS j
LEFT JOIN servico s ON s.nome = j.value;

-- Unidade no formato do HealthUnit/API (só as georreferenciadas); services segue como JSON
CREATE VIEW v_unidade AS
SELECT id, cnes, name, type, address, COALESCE(neighborhood, '') AS neighborhood,
       phone, schedule, lat, lng, services,
       before_visit AS beforeVisit, 'active' AS status,
       'official' AS dataSource, geo_source AS geoSource
FROM units
WHERE lat IS NOT NULL;

-- /api/meta
CREATE VIEW v_meta AS
SELECT
  (SELECT count(*) FROM units WHERE lat IS NOT NULL)            AS unidades_exibidas,
  (SELECT count(*) FROM units WHERE lat IS NULL)                AS unidades_sem_localizacao,
  (SELECT count(*) FROM units WHERE geo_source = 'geocoded')    AS localizacao_aproximada,
  (SELECT max(finished_at) FROM sync_log WHERE ok = 1)          AS ultima_sincronizacao,
  'Prefeitura do Recife — Portal de Dados Abertos'              AS fonte,
  'ODbL — Open Data Commons Open Database License'              AS licenca;

-- Qualidade dos dados (conferir após cada sincronização)
CREATE VIEW v_qualidade AS
SELECT type AS tipo_codigo,
       count(*)                                                   AS unidades,
       sum(geo_source = 'official')                               AS geo_oficial,
       sum(geo_source = 'geocoded')                               AS geo_aproximada,
       sum(geo_source = 'missing')                                AS sem_geo,
       sum(phone IS NULL)                                         AS sem_telefone,
       sum(schedule IS NULL)                                      AS sem_horario,
       sum(address LIKE 'Informação não disponível%')             AS sem_endereco
FROM units GROUP BY type;

-- =====================================================================
-- SEED — domínios e conteúdo (as unidades vêm da sincronização, não de seed)
-- INSERT OR IGNORE: pode rodar de novo sem duplicar.
-- =====================================================================
INSERT OR IGNORE INTO fonte_dados (codigo, descricao, url, licenca) VALUES
 ('official', 'Prefeitura do Recife — Portal de Dados Abertos: Rede de atenção à saúde no Recife',
  'https://dados.recife.pe.gov.br/dataset/rede-de-atencao-a-saude-no-recife', 'ODbL');

INSERT OR IGNORE INTO tipo_unidade (codigo, nome_completo, porta_entrada, cor_marcador, ordem) VALUES
 ('USF',                  'Unidade de Saúde da Família',              1,  'verde',    1),
 ('UBS',                  'Unidade Básica de Saúde',                  1,  'verde',    2),
 ('Centro de Saúde',      'Centro de Saúde',                          1,  'verde',    3),
 ('Policlínica',          'Policlínica',                              1,  'verde',    4),
 ('CAPS',                 'Centro de Atenção Psicossocial',           1,  'verde',    5),
 ('UPA',                  'Unidade de Pronto Atendimento',            1,  'vermelho', 6),
 ('SAMU',                 'Serviço de Atendimento Móvel de Urgência', 1,  'vermelho', 7),
 ('Maternidade',          'Maternidade',                              0, 'vermelho', 8),
 ('Hospital',             'Hospital',                                 0, 'vermelho', 9),
 ('Centro Especializado', 'Centro Especializado',                     0, 'verde',   10);

INSERT OR IGNORE INTO servico (codigo, nome, emoji, categoria_rapida, filtro_infantil, ordem) VALUES
 ('vacinacao',              'Vacinação',              '💉', 1,  1,  1),
 ('urgencia',               'Urgência',               '🚑', 1,  0, 2),
 ('atencao-basica',         'Atenção Básica',         '🩺', 1,  0, 3),
 ('saude-mental',           'Saúde Mental',           '🧠', 1,  0, 4),
 ('saude-bucal',            'Saúde Bucal',            '🦷', 1,  1,  5),
 ('saude-da-crianca',       'Saúde da Criança',       '👶', 1,  1,  6),
 ('saude-da-mulher',        'Saúde da Mulher',        '🤰', 1,  0, 7),
 ('saude-do-idoso',         'Saúde do Idoso',         NULL, 0, 0, 8),
 ('farmacia',               'Farmácia',               '💊', 1,  0, 9),
 ('exames',                 'Exames',                 '🧪', 1,  0, 10),
 ('curativos',              'Curativos',              NULL, 0, 0, 11),
 ('pre-natal',              'Pré-natal',              NULL, 0, 0, 12),
 ('planejamento-familiar',  'Planejamento Familiar',  NULL, 0, 0, 13),
 ('doencas-cronicas',       'Doenças Crônicas',       NULL, 0, 0, 14),
 ('reabilitacao',           'Reabilitação',           NULL, 0, 0, 15),
 ('especialidades',         'Especialidades',         '🏥', 1,  0, 16),
 ('puericultura',           'Puericultura',           NULL, 0, 1,  17),
 ('hipertensao-e-diabetes', 'Hipertensão e Diabetes', NULL, 0, 0, 18);

INSERT OR IGNORE INTO sinonimo_busca (termo, servico_codigo) VALUES
 ('vacinacao', 'vacinacao'),
 ('vacina', 'vacinacao'),
 ('urgencia', 'urgencia'),
 ('emergencia', 'urgencia'),
 ('pronto socorro', 'urgencia'),
 ('saude mental', 'saude-mental'),
 ('psicologo', 'saude-mental'),
 ('psiquiatra', 'saude-mental'),
 ('caps', 'saude-mental'),
 ('odontologico', 'saude-bucal'),
 ('dentista', 'saude-bucal'),
 ('saude bucal', 'saude-bucal'),
 ('pre-natal', 'pre-natal'),
 ('pre-natal', 'saude-da-mulher'),
 ('gestante', 'pre-natal'),
 ('gestante', 'saude-da-mulher'),
 ('curativo', 'curativos'),
 ('farmacia', 'farmacia'),
 ('remedio', 'farmacia'),
 ('medicamento', 'farmacia'),
 ('crianca', 'saude-da-crianca'),
 ('crianca', 'puericultura'),
 ('pediatrico', 'saude-da-crianca'),
 ('pediatria', 'saude-da-crianca'),
 ('consulta', 'atencao-basica'),
 ('exame', 'exames'),
 ('laboratorio', 'exames'),
 ('especialidade', 'especialidades'),
 ('atencao basica', 'atencao-basica'),
 ('hipertensao', 'hipertensao-e-diabetes'),
 ('hipertensao', 'doencas-cronicas'),
 ('diabetes', 'hipertensao-e-diabetes'),
 ('diabetes', 'doencas-cronicas'),
 ('idoso', 'saude-do-idoso'),
 ('planejamento familiar', 'planejamento-familiar'),
 ('reabilitacao', 'reabilitacao'),
 ('fisioterapia', 'reabilitacao');

INSERT OR IGNORE INTO emergencia_contato (id, nome, numero, descricao) VALUES
 (1, 'SAMU', '192', 'Serviço de Atendimento Móvel de Urgência. Não substitui consultas nem faz triagem médica.');

INSERT OR IGNORE INTO pagina_institucional (slug, titulo, conteudo_md) VALUES
 ('about',        'Sobre o VemSUS',  'Localizador de serviços do SUS no Recife. Iniciativa independente, não oficial. Dados da Prefeitura do Recife (ODbL).'),
 ('privacy',      'Privacidade',     'Sem cadastro, sem login. Não coletamos dados pessoais. A localização é usada apenas na sessão para achar unidades próximas.'),
 ('how-it-works', 'Como funciona',   'Informe o que precisa, veja unidades compatíveis na lista ou no mapa e abra o detalhe da unidade.');
