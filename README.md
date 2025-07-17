# Naive_RAG_For_10k_Users

Uma implementação naive (ingênua) de RAG para acesso de 10 mil usuários concorrentes.

## Diagrama de Alto Nível do Sistema

![Diagrama de Alto Nível do Sistema](docs/High-level%20Design%20%28HLD%29%20for%20Naive%20RAG%2010k%20-%20v1.png)

## Setup Ambiente de Desenvolvimento

### Dependências

- Python 3.x / pip
- venv
- Docker engine
- Git

## Scripts de Instalação/Deploy

Para o ambiente de desenvolvimento no MacOS 26, é utilizado um script: deploy.sh para - por meio do docker compose - montar as imagens dos containers dos serviços e instanciar todos os containers.

Para testar o sistema, faça o deploy local (deploy.sh) e visite http://localhost:8080

## Escalabilidade
A quantidade de containeres instanciados em cada camada do pipeline de processamento dos arquivos pdf será determinado experimentalmente.

Após a ativação dos containers, caso o script deploy.sh seja executado novamente, antes imagens e containeres antigos serão deletados, novas imagens de containers serão criadas e novos containeres serão instanciados garantindo, assim, a atualização das lógicas executadas pelos microserviços.

O usuário do ambiente de desenvolvimento poderá testar o sistema (tanto image upload quanto rag queries) na porta 8080 do localhost.

## Metadados e Ciclo de Vida das Tarefas de Processamento de Dados

O conjunto de dados de cada arquivo PDF será armazenado e transformado sendo representado por diversas estruturas de dados. Os metadados de cada documento (ou conjunto de documentos) sendo processado será representado por uma task (tarefa) que assume diferentes fases, que aqui listamos: upload pendente, upload concluido, chunknizado, embedded e vetorizado.

## API Gateway
Embora não seja implementado nesta prova de conceito, para uma implantação em ambiente de produção um API Gateway será necessário sendo posicionado entre os Serviços Expostos e a interface web do usuário para permitir a aplicação de políticas (throtling) e verificação de Token de API. Faz-se necessário implementar SSO. A aplicação Naive RAG precisaria ser cadastrada no portal do servidor de identidades para permitir a implementação de botões de login no front-end. Uma vez implementada a autenticação, tokens temporários seriam utilizados para passar pela validação do API Gateway quando nas requisições às rotas dos serviços.

## Serviços Expostos para Consumo pela Interface Web
- Upload Interface
- Chunking Config Service
- RAG Query Service

## Serviços Downstream dos Expostos Acima
- Chunking Service
- Embedding Service
- Vectorial Database Service
- Embedding LLM (pode ser self-hosted ou uma versão de 3rd-party, porém incorreria em custos)

## Serviços Necessários ao Backend

A aplicação deve suportar milhares de usuários concorrentes e isso suscita a necessidade de conseguir escalar os serviços de forma horizontal. Para isso, é interessante uma abordagem que maximize o desempenho e a utilização dos serviços. Inspirado em arquiteturas de computadores modernos, eu decidi não fazer o processamento fim-a-fim dos documentos no exato momento em que são submetidos pelo usuário. Pelo contrário, há de se imaginar que diferentes serviços poderão trabalhar em diferentes fases do ciclo de vida dos dados dos arquivos PDF de forma que possamos fazer o provisionamento da quantidade correta de capacity para cada uma. Esse tipo de quebra das implementações monolíticas começou na forma do SOA (service-oriented architecture) e foi posteriormente intensificada pela abordagem de microserviços.

Dito isso, para o endpoint da API que trataria o upload de arquivos PDF, é interessante e necessário outros endpoints em outros serviços para fazer as etapas subsequentes de transformação do dado dos arquivos PDF, sendo elas: chunking, geração de embeddings e armazenamento em banco de dados vetorial (para habilitar consultas futuras feitas pelo RAG).

### Master Task Database Service
Registra todas as tarefas em andamento no sistema, recebendo também sinais de heartbeat dos serviços que estão trabalhando em cada uma delas. Isso dá ao sistema a capacidade de detectar que um container está em falha e então regredir o status da tarefa para que outro container possa assumir o processamento dali em diante. Essa capacidade nos permite não utilizar armazenamento persistente em alguns serviços, dando a eles maior desempenho por manter todo o dado em memória.

### ChunkConfig Service
Por simplicidade, assumiremos que a única estratégia de chunking a ser configurada nesta versão do sistema será a de tamanhos fixos com 2 parâmetros configuráveis: chunk size (tamanho do chunk) e overlapping (% de sobreposição entre chunks vizinhos). Em caso de expansão futura na API, um parametros chunk strategy (estratégia de chunknização) definida como um tipo enumerador permitirá à API receber outras estrategias no formato JSON tais como: quebra por sentença ou parágrafo.

### Upload Service

Permite o upload de 1 ou mais arquivos PDF e tem como única responsabilidade armazenar em "disco" (storage) os arquivos recebidos. Isso é interessante, pois, desde já torna-se possível catalogar. O Upload Service também é responsável por registrar um índice com nomes de arquivos pdf e a fase do ciclo de vida deles (nesta fase eles são considerados "upload concluido").

#### Serviços em "Downstream" (subsequentes) ao Upload Service
- Chunking Service: dá continuidade nas tasks no estado "upload concluido" consultando os arquivos e transformando-os em chunks, bem como consultando o ChunkConfig Service para seguir a estratégia e parâmetros de chunking definidos anteriormente. Este serviço precisa se inscrever para "escutar" atualizações de parâmetros divulgadas pelo Chunking Config Service, ou consultá-lo de forma síncrona caso uma task apareça antes de receber a notificação de quais parâmetros de chunking utilizar.
Para ter um melhor desempenho, os chunks do Chunking Service serão gerados e permanecerão em um buffer memória principal até que sejam consumidos pelo serviço subsequente.
- Embedding Service: consome os chunks do buffer do Chunking Service, submetendos estes à requisição a um modelo de linguagem de embeddings para então obter a representação vetorial destes dados.  Estas representações vetoriais serão armazenadas em um novo buffer, do próprio Embedding Service, onde permanecerão com o status da task "chunknizado" até que sejam consumidos pelo próximo serviço. A respeito dos modelo de linguagem de embeddings, existem rankings evidenciando que modelos open source atingiram acuária similar aos modelos proprietários em zero-shot.
- Vectorial Database Service: consome os "embeddings" (representação vetorial de dados) do Embedding Service, armazenando-os em um SGBD especializado.

A respeito dos buffers, todos os citados acima poderiam ser melhor implementados se não o forem como um buffer em memória, mas sim filas (Queues) ofertadas nos provedores de serviços de nuvem, tais como Amazon SQS. Isso aumenta a resiliência do sistema, tirando a responsabilidade de um container cuja implementação de gestão do buffer poderia ter erros. Além disso torna-se possível implementar Dead Letter Queues (filas de tarefas que falharam) para guardar tarefa que falharam em processamento e então tentar um redrive (nova tentiva de execução). Outra vantagem de usar os SQS é a integração com o AWS CloudWatch (serviço de logs centralizados) para automatizar a geração de alarmes com grandes ganhos de observabilidade do sistema.


### RAG Query Service: 
Faz o fluxo simplificado de consultas ao LLM. A query do usuário é convertida em embeddings (aproveitando os serviços existentes) para então se fazer uma consulta à base vetorial, que retornará chunks semanticamente relevantes, pois, os vetores armazenados possuem em seus metadados os identificadores dos chunks que os constituíram. Então, o RAG Query Service vai formatar um prompt para enviar ao Chat LLM (seja este opensource ou prorietário, self-hosted ou não) de tal forma que o prompt estará enriquecido com informações relevantes e assim o LLM terá maiores chances de elaborar uma boa resposta à query do usuário.

