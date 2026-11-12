# Domínio e publicação — avaliação

## Vale a pena ter domínio próprio? Sim, e por motivo técnico
A API de geolocalização do navegador (`navigator.geolocation`, usada para "perto de você") **só funciona em HTTPS**. HTTPS confiável pede um nome de domínio. Além disso, domínio dá confiança (quem busca saúde desconfia de link estranho), permite e-mail de contato (exigido também pelo Nominatim) e deixa você trocar de hospedagem sem mudar o endereço.

## Opções
| Opção | Quando serve | Observações |
|---|---|---|
| **Subdomínio da plataforma** (`vemsus.fly.dev`, `*.onrender.com`…) | Teste, demonstração, validação com usuários | Grátis ou barato, HTTPS incluso; aparência provisória |
| **`.com.br` ou `.org.br` no Registro.br** | Projeto independente (cidadão, ONG, coletivo) | Exige CPF/CNPJ e, no caso do `.org.br`, perfil de entidade sem fins lucrativos — **confirme a elegibilidade e o valor atual no Registro.br**. Não consegui verificar disponibilidade de nomes daqui: consulte `vemsus.com.br`, `vemsus.org.br` etc. |
| **Subdomínio oficial `…recife.pe.gov.br`** | Se o VemSUS virar iniciativa da Prefeitura/Secretaria de Saúde | Só a própria prefeitura (Emprel/Sesau) concede. É o caminho de maior credibilidade; vale procurar o *Hacker Cidadão* / *Inovação Aberta* do Recife |
| `.gov.br` / `.saude.gov.br` | — | Reservados a órgãos de governo; não use nada que imite domínio oficial |

## Cuidado de marca e responsabilidade
"SUS" é marca do Ministério da Saúde. Enquanto o app for independente, deixe explícito no site e no domínio/rodapé: **"Iniciativa independente, não oficial. Dados: Prefeitura do Recife (ODbL)."** O app orienta, não substitui o serviço de saúde — mantenha o aviso do SAMU 192. Vale uma consulta jurídica antes de divulgar amplamente.

## Como publicar (arquivos prontos em `deploy/`)
1. VPS pequena (1 vCPU / 1 GB basta: são centenas de unidades em memória) **ou** Fly.io/Render/Railway usando o `Dockerfile`.
2. Aponte o DNS (`A`/`AAAA`) do domínio para o servidor. Cloudflare na frente é opcional.
3. `cp backend/.env.example backend/.env` e preencha `CKAN_API_TOKEN`, `ADMIN_TOKEN` (longo e aleatório), `NOMINATIM_USER_AGENT` (com seu e-mail real) e `ALLOWED_ORIGINS=https://seudominio.com.br`.
4. `cd deploy && DOMAIN=seudominio.com.br docker compose up -d --build` — o Caddy emite e renova o certificado sozinho.
5. Teste: `https://seudominio.com.br/api/meta` (deve mostrar `ready: true` após a primeira sincronização).
6. Agende backup do volume `vemsus-data` (opcional: o dado se reconstrói do portal com `POST /api/admin/sync`).

## Checklist antes de divulgar
- [ ] Token anterior revogado se esteve no front/Git
- [ ] Tiles de mapa com provedor adequado ao volume de acessos
- [ ] Página "Sobre/Privacidade" com fonte, licença ODbL, data da última atualização (`/api/meta`) e aviso de "independente"
- [ ] CSP (Content-Security-Policy) no Caddy, testada com o mapa funcionando
- [ ] Monitoramento simples de `/api/health` (UptimeRobot ou similar)
