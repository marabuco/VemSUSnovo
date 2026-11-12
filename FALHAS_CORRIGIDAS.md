# Falhas do protótipo e como foram corrigidas

| # | Falha no protótipo | Risco | Correção |
|---|---|---|---|
| 1 | Token da Prefeitura lido de `import.meta.env.VITE_RECIFE_API_TOKEN` | Variáveis `VITE_*` vão **dentro do JavaScript público**: qualquer pessoa extrai o token | Só o backend usa o token (`CKAN_API_TOKEN`, no `.env` do servidor). **Se o token já foi publicado/compartilhado, gere outro no portal.** |
| 2 | `MOCK_MODE = true` fixo + `catch {}` que cai silenciosamente nos dados fictícios | Em saúde, mostrar endereço/telefone inventado como real leva a pessoa ao lugar errado | Dados reais por padrão; se a API falhar, o app mostra um erro claro. Mock só com `VITE_ALLOW_MOCK=true` (dev) |
| 3 | Unidade sem coordenada recebia `-8.0580, -34.8958` (coordenada inventada) e `Number(x \|\| …)` tratava 0 como vazio | Marcador no lugar errado; distância e ranking falsos | `geo.py`: valida a caixa do Recife, corrige vírgula decimal, sinal perdido e lat/lng invertidas; sem coordenada válida tenta Nominatim/OSM (marcado `geoSource: "geocoded"`); se nada serve, a unidade **não** vai ao mapa — nunca inventa |
| 4 | Nomes de campos chutados (`nome`, `ds_estabelecimento`, `tp_unidade`…) | Normalização falhava em silêncio | Esquema real do dataset: `tipo_unidade, nome_oficial, cnes, tipo_servico, endereço, bairro, fone, especialidade, como_usar, horario, latitude, longitude` |
| 5 | `limit=500` sem paginação; cada linha virava uma unidade | Dados cortados; a mesma unidade repetida uma vez por serviço | Paginação completa (`offset`) e agrupamento por CNES, unindo serviços e horários |
| 6 | `id: String(raw.id \|\| Math.random())` | IDs mudam a cada carga: unidade selecionada se perde, links não funcionam | ID estável `cnes-<n>` (ou hash de nome+endereço) |
| 7 | `detectUnitType` com `includes('upa')` | "ocupacional", "equipamento"… viravam UPA; tipo desconhecido virava "Centro de Saúde" sem aviso | Regex com palavra inteira; tipos não reconhecidos entram no diagnóstico (`/api/admin/diagnostico`) |
| 8 | `parseServices` devolvia `['Atenção Básica']` quando não achava nada | Prometia serviço que a unidade pode não oferecer | Sem serviço padrão. Só o inerente ao tipo (USF/UBS → Atenção Básica, UPA → Urgência, CAPS → Saúde Mental…), documentado em `normalize.py` |
| 9 | `scoreUnit` com termo vazio: `includes('')` é sempre `true` → +30 para todas | Ranking sem sentido na listagem sem busca | Termo vazio não pontua |
| 10 | Busca sem normalizar acentos, só frase inteira (`'vacinacao'` ≠ `'vacinação'`; "vacina criança" não achava nada) | Quem digita sem acento não encontra | Normalização sem acento + busca por palavras + sinônimos (`synonyms.py`, portado do `SERVICE_MAP`) |
| 11 | `sort` recalculando o score a cada comparação | Lento com milhares de unidades | Score calculado uma vez por unidade |
| 12 | Chave `'curativo'` duplicada no `SERVICE_MAP` | Erro de TypeScript estrito (TS1117) | Removida |
| 13 | Nenhuma resiliência a falha do portal | App fora do ar se o portal cair | Snapshot em SQLite: o último dado bom continua servido; sincronização diária; retentativas |
| 14 | Localização do usuário sem cuidado de privacidade | Brief promete "sem coleta de dados pessoais" | `Cache-Control: no-store`, sem access log (uvicorn/Caddy), validação de lat/lng, nada de IP gravado, CORS restrito, rate-limit em memória |
| 15 | Atribuição da fonte ausente | A licença **ODbL** exige citar a fonte | `/api/meta` entrega fonte, licença e data da última sincronização para o rodapé/"Sobre" |

## O que ainda depende de você / não pude verificar
* O sandbox onde construí **não alcança** `dados.recife.pe.gov.br`; os testes usam um CKAN simulado no formato real. **No primeiro `sync` real**, abra `/api/admin/diagnostico` e confira `unmapped_type_values` e `coords_invalid` — é ali que se ajustam as regras de `normalize.py`.
* Não recebi os componentes React: falta ligar `searchUnits`/`fetchMeta` nas telas, mostrar o aviso **"localização aproximada"** quando `geoSource === 'geocoded'` e o crédito da fonte no rodapé.
* O mapa Leaflet usa tiles públicos do OpenStreetMap. A política deles não permite uso pesado em produção: com tráfego real, use um provedor de tiles (com chave) ou hospede o seu.
* `status` das unidades vem como `active`: o dataset não informa se a unidade está funcionando hoje. A tela deve manter o "Antes de ir — orientações oficiais".
