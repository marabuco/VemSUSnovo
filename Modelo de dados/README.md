# Banco de dados — VemSUS

Banco **SQLite** do VemSUS, com os dados abertos da Prefeitura do Recife (rede de atenção à saúde). O arquivo do banco é gerado em `backend/data/vemsus.db`.

**Navegação rápida**

- [`vemsus_schema_sqlite.sql`](vemsus_schema_sqlite.sql): script único com tabelas, índices, views e dados iniciais
- [`MODELO_DADOS.md`](MODELO_DADOS.md): diagrama ER, origem de cada coluna e garantias do banco
- [Como executar](#como-executar)
- [Tabelas](#tabelas) · [Views](#views) · [Dados iniciais](#dados-iniciais-seed)
- [Relação com o backend](#relação-com-o-backend)
- [← README principal do projeto](../README.md)

---

## Como executar

Os comandos partem da **raiz do repositório**. O script é idempotente: pode rodar mais de uma vez sem erro nem duplicação.

**Opção 1 — CLI do SQLite** (`sqlite3`)

```bash
mkdir -p backend/data
sqlite3 backend/data/vemsus.db < database/vemsus_schema_sqlite.sql
```

**Opção 2 — só com Python** (não exige instalar nada além do Python)

```bash
mkdir -p backend/data
python -c "import sqlite3; c=sqlite3.connect('backend/data/vemsus.db'); c.executescript(open('database/vemsus_schema_sqlite.sql', encoding='utf-8').read()); print('ok')"
```

Verificação rápida:

```sql
SELECT count(*) FROM servico;        -- 18
SELECT count(*) FROM tipo_unidade;   -- 10
SELECT * FROM v_meta;                -- fonte e licença (0 unidades até a 1ª sincronização)
```

> **Rodar o script é opcional.** O backend cria `units`, `geocode_cache` e `sync_log` sozinho ao iniciar. O script acrescenta as tabelas de domínio, as views e os dados iniciais, e serve como documentação e entrega do modelo.
> Se o banco já existir, o `CREATE TABLE IF NOT EXISTS` **não altera** tabelas já criadas. Em desenvolvimento, para recriar do zero, apague `backend/data/vemsus.db` e rode o script de novo (o backend recarrega as unidades na próxima sincronização).

---

## Tabelas

Os links abrem o trecho exato no [`vemsus_schema_sqlite.sql`](vemsus_schema_sqlite.sql). Se o script for editado, os números de linha podem precisar de ajuste.

| Grupo | Tabela | Função |
|---|---|---|
| Domínios | [`fonte_dados`](vemsus_schema_sqlite.sql#L26) | Origem dos dados (portal da Prefeitura) e licença |
| | [`tipo_unidade`](vemsus_schema_sqlite.sql#L33) | Tipos de unidade (USF, UBS, UPA, CAPS, Hospital etc.) |
| | [`servico`](vemsus_schema_sqlite.sql#L41) | As 18 tags de serviço exibidas no app |
| | [`sinonimo_busca`](vemsus_schema_sqlite.sql#L51) | Dicionário popular → serviço (ex.: "dentista" → Saúde Bucal) |
| **Usadas pelo backend** | [`units`](vemsus_schema_sqlite.sql#L61) | Unidades de saúde, com georreferenciamento validado; os serviços ficam em uma lista JSON |
| | [`geocode_cache`](vemsus_schema_sqlite.sql#L89) | Cache do Nominatim/OpenStreetMap |
| | [`sync_log`](vemsus_schema_sqlite.sql#L98) | Histórico de cada sincronização com o portal |
| Previstas no modelo | [`ckan_registro_bruto`](vemsus_schema_sqlite.sql#L114) | Staging com as linhas exatas do CKAN |
| | [`emergencia_contato`](vemsus_schema_sqlite.sql#L139) | Contatos de urgência (SAMU 192) |
| | [`emergencia_situacao`](vemsus_schema_sqlite.sql#L146) | Itens de "Quando ligar?" |
| | [`pagina_institucional`](vemsus_schema_sqlite.sql#L153) | Sobre, Privacidade e Como funciona |
| | [`texto_interface`](vemsus_schema_sqlite.sql#L160) | Textos da interface, com versão simplificada (modo infantil) |
| | [`evento_busca`](vemsus_schema_sqlite.sql#L167) | Métrica anônima e opcional (sem IP, sem localização) |

Diagrama ER e origem de cada coluna: [`MODELO_DADOS.md`](MODELO_DADOS.md).

## Views

| View | Uso |
|---|---|
| [`v_unidade_servico`](vemsus_schema_sqlite.sql#L187) | Relação unidade × serviço, desdobrada da lista JSON de `units.services` |
| [`v_unidade`](vemsus_schema_sqlite.sql#L193) | Unidade no formato da API (`HealthUnit`), só as georreferenciadas |
| [`v_meta`](vemsus_schema_sqlite.sql#L202) | Dados do endpoint `/api/meta`: contagens, última sincronização, fonte e licença |
| [`v_qualidade`](vemsus_schema_sqlite.sql#L212) | Qualidade dos dados por tipo de unidade, para conferir após cada sincronização |

Exemplo: unidades que oferecem Vacinação.

```sql
SELECT u.name, u.neighborhood
FROM units u JOIN v_unidade_servico vs ON vs.unidade_id = u.id
WHERE vs.servico_nome = 'Vacinação' AND u.lat IS NOT NULL;
```

## Garantias que o banco impõe

- Coordenada fora do Recife é rejeitada (`CHECK` em `lat` e `lng`).
- `geo_source = 'missing'` só existe sem coordenada: nunca há posição inventada.
- `geo_source` só aceita `official`, `geocoded` ou `missing`.
- `services` precisa ser uma lista JSON válida.
- Tipo de unidade referencia `tipo_unidade`. O SQLite só aplica chaves estrangeiras com `PRAGMA foreign_keys = ON`, e o backend não ativa esse pragma; por isso a validação de tipo é feita pelo código do backend.
- O banco não guarda dado pessoal: sem login, cadastro ou localização do usuário.

## Dados iniciais (seed)

A partir da [linha 224](vemsus_schema_sqlite.sql#L224), o script carrega: 1 fonte de dados, 10 tipos de unidade, 18 serviços, 37 sinônimos de busca, o contato SAMU 192 e 3 páginas institucionais. As **unidades não vêm de seed**: entram pela sincronização com o [portal de dados abertos](https://dados.recife.pe.gov.br/dataset/rede-de-atencao-a-saude-no-recife) (licença ODbL).

## Relação com o backend

- As tabelas `units`, `geocode_cache` e `sync_log` têm as **mesmas colunas, na mesma ordem** do [`backend/app/db.py`](../backend/app/db.py). O backend grava com `INSERT` posicional, então **não acrescente nem reordene colunas** dessas tabelas.
- A busca com ranking, a distância (haversine) e a remoção de acentos ficam no Python ([`backend/app/search.py`](../backend/app/search.py)). O SQLite não tem essas funções, então o script não as define.
- O modelo original em PostgreSQL separava `unidade` e `unidade_servico`. Aqui, `units` corresponde a `unidade`, e a view `v_unidade_servico` faz o papel de `unidade_servico`.

## Boas práticas

- Nunca commite o arquivo `backend/data/vemsus.db` (já está no `.gitignore`); ele se reconstrói pela sincronização.
- Ao alterar o script, atualize também o [`MODELO_DADOS.md`](MODELO_DADOS.md).
- Convenções do repositório: commits no padrão Conventional Commits (ex.: `feat(db): ...`) e alterações na `main` via Pull Request.
