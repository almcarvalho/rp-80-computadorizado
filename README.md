# Redutor de ruído para rádio PX

Aplicativo Python para ouvir no computador o áudio recebido pela saída de fone de um rádio PX. Mostra a onda sonora de saída, permite selecionar entrada e saída, ajustar o volume, ativar ou desativar a redução de ruído e aplicar um filtro para a faixa da voz. O processamento é ao vivo e introduz atraso; não altera o sinal transmitido pelo rádio.

## Ligação

1. Diminua o volume do rádio e do computador antes de conectar tudo.
2. Conecte a **saída de fone** do rádio à **entrada de linha** do computador ou de uma interface de áudio USB, usando cabo e adaptadores adequados às conexões. Não conecte a saída de alto-falante de potência diretamente ao computador. Consulte o manual do rádio antes de conectar uma saída externa: alguns modelos usam saídas incompatíveis com o aterramento de uma placa de som; se necessário, use uma interface isolada adequada.
3. Se houver apenas entrada de microfone, use uma interface USB com entrada de linha ou um atenuador apropriado: uma entrada de microfone pode saturar com sinal de fone. Uma saída de fone do computador não é uma entrada de áudio; conectores combinados de headset podem exigir adaptador ou interface apropriada.
4. Conecte fones ou caixas à saída do computador. Suba o volume do rádio aos poucos. Se o som distorcer, reduza o volume do rádio ou o nível de entrada nas configurações do sistema. Selecione a entrada correta nas configurações do sistema e permita acesso ao microfone para aplicativos, se solicitado.

## Instalação no Windows

Instale Python 3.10 ou superior, incluindo o gerenciador `pip` e o Tkinter (normalmente incluído no instalador do Windows). Abra o PowerShell na pasta deste projeto e crie o ambiente virtual:

```powershell
py -m venv .venv
```

Instale as bibliotecas **uma por vez**, executando cada comando abaixo:

```powershell
.\.venv\Scripts\python.exe -m pip install "numpy>=1.24,<3"
.\.venv\Scripts\python.exe -m pip install "scipy>=1.10,<2"
.\.venv\Scripts\python.exe -m pip install "sounddevice>=0.4.6,<1"
.\.venv\Scripts\python.exe -m pip install "noisereduce>=3.0,<4"
.\.venv\Scripts\python.exe -m pip install "vosk>=0.3.45,<1"
```

Os limites de versão são os mesmos de `requirements.txt`. Os comandos usam o Python do ambiente virtual, sem precisar ativá-lo. Depois, inicie o programa:

```powershell
.\.venv\Scripts\python.exe app.py
```

No Linux ou macOS, crie o ambiente com `python3 -m venv .venv` e execute os mesmos comandos de instalação, substituindo `.\.venv\Scripts\python.exe` por `.venv/bin/python`. Para iniciar, use `.venv/bin/python app.py`. Dependendo da distribuição, pode ser necessário instalar Tk e PortAudio pelos pacotes do sistema.

## Uso

O painel espacial inclui um globo giratório: clique em um país visível ou digite o nome completo ou número da divisão e pressione Enter ou **Buscar país ou divisão**. O alfabeto fonético fica na faixa inferior, ao lado dos botões de áudio. As divisões foram extraídas de `divisao.pdf` e ficam em `divisoes.json`, inclusive as que o documento marca como excluídas. É possível pesquisar todas pelo número; alguns territórios e ilhas não têm um polígono correspondente no mapa e só aparecem na pesquisa. Os nomes sem correspondência no mapa permanecem como no PDF, em inglês. A lista reflete o documento fornecido e não foi atualizada por fonte externa. Os contornos são do [Natural Earth](https://www.naturalearthdata.com/), conjunto de dados de domínio público; o mapa é ilustrativo e não deve ser usado para navegação ou delimitação precisa.

Arraste o globo para os lados com o botão esquerdo do mouse para girá-lo manualmente; a rotação automática pausa. Clique em **Retomar rotação** para voltar ao movimento automático. Para ampliar o globo e a onda sonora, clique em **Tela cheia**; pressione **Esc** ou use o botão na tela para retornar. O áudio continua funcionando durante a visualização.

Ao abrir a tela cheia, o indicativo digitado aparece no canto superior esquerdo junto do nome salvo no log, quando houver. Os números no início do indicativo são usados para selecionar a divisão no globo automaticamente; por exemplo, `3OZO001` seleciona a divisão 3. Se o número não estiver cadastrado, a tela informa isso.

Ao buscar uma divisão, o globo para e desenha uma rota aproximada desde o centro do Brasil até o destino. Clique em **Retomar rotação** para girar novamente. As coordenadas aproximadas dos destinos são da [lista de divisões do Romeo Charlie](https://www.rcqsl.com/dx-divisions-list.php), guardadas em `coordenadas_divisoes.json`; não representam a posição da sua estação e não são uma medição de propagação. Divisões excluídas não recebem rota.

Marque **Propagação 11 m (MUF)** para consultar os contornos ionosféricos de [KC2G / GIRO](https://prop.kc2g.com/about/), atualizados aproximadamente a cada 15 minutos. As linhas azuis representam contornos de MUF(3000 km) abaixo de 27 MHz; as vermelhas, contornos de 27 MHz ou mais. Os valores são da ionosfera na região de cada linha, não uma previsão de contato a partir do Brasil ou um mapa de intensidade de sinal. A estimativa interpola medições esparsas, pode estar defasada e não garante uma abertura; a propagação depende também do percurso, antenas e outros fatores. O horário exibido é a última modificação informada pelo servidor, convertida para o fuso do computador. É necessária conexão com a internet.

Para procurar a entrada do rádio, clique em **Procurar** na seção de dispositivos de áudio. O programa verifica cada entrada disponível durante cerca de 4 segundos e sugere a que tem sinal mais forte. Aguarde a verificação terminar com o rádio ligado e emitindo áudio. A detecção não reconhece especificamente um rádio: microfones ou outras fontes podem ser escolhidos; confirme a sugestão ouvindo e altere a seleção se necessário. Entradas incompatíveis são ignoradas. Quanto mais entradas houver, mais tempo levará a verificação. Para procurar novamente, pare o áudio primeiro.

Para procurar um contato, digite o **indicativo completo** no campo junto a Sistema de áudio e clique em **HamDB**. A consulta usa a API pública [HamDB](https://hamdb.org/api), exige internet e envia o indicativo pesquisado à HamDB. Ela é voltada a indicativos de radioamador, tem cobertura limitada e pode não encontrar indicativos de grupos PX de 11 metros; apenas o número da divisão não identifica um operador. As buscas concluídas, encontradas ou não, são salvas em `buscas_contatos.jsonl` e podem ser vistas em **Log**, das mais recentes às mais antigas. Para resultados não encontrados, o histórico mostra o indicativo e o horário. Apague esse arquivo para limpar o histórico. Falhas de conexão e consultas inválidas não são gravadas como não encontradas.

O botão **WRL** consulta os perfis da busca pública do site World Radio League. Digite o indicativo completo: o programa verifica uma correspondência exata entre as primeiras cinco sugestões e mostra os dados disponíveis. A busca usa a configuração pública publicada pelo site, sem enviar sua chave pessoal. Como essa interface não está documentada na API oficial `wrl.json`, ela pode mudar ou deixar de funcionar; nesse caso, a mensagem de erro será exibida. Consultas sem resultado também entram no log. A variável `WRL_API_KEY` no `.env` é reservada para a API de contatos pessoais e não é usada nessa busca pública. Nunca compartilhe nem envie o arquivo `.env` para o repositório.

Os botões consultam fontes independentes: **WRL** consulta apenas a WRL e **HamDB** consulta apenas a HamDB. Na caixa do indicativo, **Enter** ou **Tab** procura primeiro um nome no histórico local. Se encontrar, mostra o contato com as opções **Fechar** e **Google**; se não encontrar, abre a busca no Google. A coluna **Fonte** no log identifica o serviço consultado.

Para adicionar ou corrigir um nome no histórico, abra **Log**, selecione a linha e digite no campo **Nome do contato selecionado**. A alteração é salva automaticamente enquanto você digita e permanece ao fechar o log ou o programa.

Ao pesquisar novamente um indicativo, o programa mostra imediatamente o nome conhecido mais recente no histórico, seja ele editado manualmente ou encontrado em uma base. Nas buscas pelos botões WRL ou HamDB, a consulta escolhida continua normalmente; nomes ausentes ou marcados como não encontrados são ignorados.

O botão **Google** abre no navegador uma pesquisa usando exatamente o texto digitado na caixa, sem acrescentar termos. O resumo de IA, quando disponível, é exibido pelo próprio Google na página de resultados; sua exibição não é garantida e ele não é importado para o aplicativo nem para o log de buscas. A busca envia o texto ao Google e está sujeita às configurações da conta e da região.

Ao executar o aplicativo pelo terminal, as consultas à API HamDB mostram a chamada, o estado HTTP e a resposta JSON ou o erro. As respostas podem conter informações públicas do contato. A busca do botão Google abre o navegador e não retorna uma resposta de API ao programa.

1. Selecione a entrada à qual o rádio está conectado e a saída em que deseja ouvir. Clique em **Atualizar lista** se conectar um dispositivo depois de abrir o programa.
2. Clique em **Iniciar**. Aguarde um intervalo sem fala, com o chiado típico presente, e clique em **Capturar ruído (2 s)**. Evite fala durante a captura. É possível repetir a captura quando o ruído mudar; a amostra é descartada ao parar.
3. Ajuste **Intensidade da redução**, **Volume de saída** e **Realçar voz**. Desmarque **Redução de ruído** para comparar. A redução só começa a funcionar depois da captura. O filtro de voz e o volume continuam independentes dessa seleção.
4. Clique em **Parar** para encerrar o áudio. Para trocar dispositivos, pare primeiro.

Se não ouvir som, confira dispositivos, volumes, permissões e conexão. Se houver distorção, reduza o nível na origem e o volume de saída; ganho excessivo causa cortes no sinal. Caso haja cortes ou travamentos, feche outros programas, diminua a intensidade ou desative a redução. O programa usa 44.100 Hz em mono; dispositivos que não aceitam essa configuração podem precisar de outra configuração no sistema ou de uma interface diferente. Algumas combinações de dispositivos/driver não permitem abrir entrada e saída juntas. O gráfico mostra o áudio processado, não o sinal de rádio RF.

## Bibliotecas

A redução usa [noisereduce](https://github.com/timsainb/noisereduce), biblioteca open source conhecida em Python, com redução espectral baseada na amostra do chiado. Não há uma classificação universal verificável que permita afirmar que seja a biblioteca mais usada. A captura e reprodução usam [python-sounddevice](https://python-sounddevice.readthedocs.io/), baseada em PortAudio; NumPy e SciPy realizam operações e filtragem, e Tkinter fornece a interface. A eficácia varia conforme o ruído: interferências fortes ou parecidas com voz podem permanecer, e ajustes agressivos podem deformar a fala.

## Legendas e log de conversas

As legendas usam [Vosk](https://alphacephei.com/vosk/) localmente, sem enviar áudio para a internet. Baixe os modelos dos idiomas que deseja usar e extraia cada pasta ao lado de `app.py`:

- [Português](https://alphacephei.com/vosk/models/vosk-model-small-pt-0.3.zip): pasta `vosk-model-small-pt-0.3`.
- [Inglês](https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip): pasta `vosk-model-small-en-us-0.15`.
- [Espanhol](https://alphacephei.com/vosk/models/vosk-model-small-es-0.42.zip): pasta `vosk-model-small-es-0.42`.

Dentro de cada pasta extraída devem estar diretamente os arquivos e pastas do modelo, como `am` e `conf`. Não é necessário baixar os modelos dos idiomas que não for usar.

Escolha **Português**, **Inglês** ou **Espanhol**, marque **Ativar legendas** e inicie o áudio. Selecione o idioma falado no rádio; o programa transcreve nesse idioma, sem tradução nem detecção automática. Para trocar o idioma, desmarque **Ativar legendas**, escolha outro idioma e marque novamente. Na tela principal, a faixa preta abaixo da onda mostra palavras parciais enquanto são reconhecidas. As frases concluídas aparecem no botão **📖 Log**, no canto superior direito, da mais recente para a mais antiga, com data e horário. As frases são salvas em `conversas.jsonl` na pasta do programa e permanecem disponíveis após reiniciar; apague esse arquivo para limpar o histórico. Ao desativar as legendas ou parar o áudio, a última frase em processamento ainda pode ser concluída e registrada. As legendas não são gravadas durante a busca de entradas.

A transcrição é uma estimativa e pode errar ou deixar de reconhecer palavras, especialmente com chiado, códigos de rádio e conversas simultâneas. O processamento pode atrasar ou perder trechos se o computador não acompanhar; nesse caso uma mensagem será exibida.

O reconhecimento recebe o áudio após a redução de ruído, mas antes do filtro de voz e do volume de saída. A redução só atua quando estiver ativada e houver uma amostra de chiado capturada; caso contrário, o reconhecimento recebe a entrada original. Uma redução excessiva pode prejudicar a fala e a transcrição. Se as legendas não aparecerem, confirme a entrada selecionada e o nível de entrada no Windows, verifique se há voz audível no rádio e teste com uma fala clara. O log recebe frases concluídas, que podem demorar até uma pausa ou até parar o áudio.
