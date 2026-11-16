VemSUS
Localizador inteligente de serviços do SUS para cidadãos do Recife. O projeto foi desenvolvido com React, TypeScript, Vite e Tailwind CSS, com mapa baseado em Leaflet e OpenStreetMap.
Funcionalidades
busca de unidades por serviço, bairro ou endereço;
filtros por serviço e tipo de unidade;
ordenação considerando compatibilidade e proximidade;
geolocalização do usuário;
visualização em lista e mapa;
detalhes das unidades;
orientação para emergências pelo SAMU 192;
modo infantil, modo escuro e recursos de acessibilidade;
dados mockados com integração preparada para a API de Dados Abertos do Recife.
Requisitos
Node.js 22 ou superior;
pnpm 10 ou superior.
As versões recomendadas também estão registradas em `.mise.toml`.
Instalação
```bash
git clone URL\\\_DO\\\_SEU\\\_REPOSITORIO
cd vemsus
pnpm install
cp .env.example .env.local
pnpm dev
```
O token da API é opcional. Sem ele, a aplicação usa automaticamente os dados mockados incluídos no projeto.
Variáveis de ambiente
Variável	Obrigatória	Descrição
`VITE\\\_RECIFE\\\_API\\\_TOKEN`	Não	Token para consultar a API de Dados Abertos da Prefeitura do Recife.
Nunca publique o arquivo `.env.local` ou tokens reais no GitHub.
Scripts
```bash
pnpm dev       # ambiente de desenvolvimento
pnpm build     # build de produção
pnpm preview   # pré-visualização do build
pnpm format    # formatação do código
```
Estrutura principal
```text
src/
├── components/   # componentes e telas
├── data/         # dados mockados
├── services/     # consulta, normalização e filtros
├── App.tsx       # estado e navegação principal
├── index.css     # estilos globais e tema
└── main.tsx      # ponto de entrada
public/           # documentação e mapas para download
```
Publicação no GitHub
O conteúdo deste repositório já está pronto para versionamento. Se você baixou o pacote ZIP disponibilizado no rodapé da aplicação:
```bash
unzip vemsus-codigo-fonte.zip
cd vemsus-codigo-fonte
git init
git add .
git commit -m "Publica código-fonte do VemSUS"
