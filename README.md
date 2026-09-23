# Upscale local

Aplicativo Python simples para ampliar imagens localmente. O modo padrão usa Lanczos e recuperação de bordas; se encontrar um modelo OpenCV `.pb` em `models/`, o modo `auto` tenta usar super-resolução por IA e volta ao pipeline local se a dependência não estiver instalada.

## Instalação

```powershell
cd C:\Users\Brenno\Desktop\Upscale
python -m pip install -r requirements.txt
```

Os três modelos compatíveis já ficam em `models/`: `EDSR_x4.pb`, `FSRCNN_x4.pb` e `ESPCN_x4.pb`. A seleção automática limita a maior dimensão da saída a 2048 px para EDSR e 4096 px para FSRCNN/ESPCN. A escala do modelo precisa ser igual à escala solicitada.

## Uso

Interface gráfica:

```powershell
python .\upscale_app.py --gui
```

Linha de comando:

```powershell
python .\upscale_app.py "C:\Users\Brenno\Downloads\HS0lKUAa8AETRKm.jpg" -s 4 -o .\saida.png
```

Com IA obrigatória:

```powershell
python .\upscale_app.py entrada.jpg --mode ai --model .\models\EDSR_x4.pb -s 4
```

O modo `--laya` é opcional. Ele lê `LAYA_KEY` de `.env` e chama `https://wire.ia.br/v1/decide` com o contrato tipado do Laya. A API recebe somente largura, altura, extensão, escala e disponibilidade de modelo local; não recebe a imagem. Na GUI, marque `Decidir com Laya`. Se a API estiver indisponível, sem chave ou retornar uma escolha incompatível, o processamento local continua.

Para configurar a chave sem colocá-la no código:

```powershell
Copy-Item .\.env.example .\.env
# Edite .env localmente e preencha LAYA_KEY; não cole a chave no terminal compartilhado.
```

## Limitação importante

Upscale aumenta resolução e pode recuperar bordas; não recupera detalhes que não estão no original. Modelos de IA podem criar detalhes plausíveis e incorretos. Para texto escaneado, mantenha o original e compare a saída antes de publicar.

## Android

O app Android se chama PixelForge e fica em `android/`. Ele usa Material 3 com tema azul, aceita múltiplas imagens e vídeos, mas processa a fila serialmente. Imagens usam FSRCNN x4 e são limitadas a 4K; vídeos usam o Transformer do Media3 para escala leve com aceleração do dispositivo e preservação do áudio.

Para compilar localmente com Android Studio, abra a pasta `android/`. O workflow `.github/workflows/android.yml` compila `app-debug.apk` e publica o arquivo como artefato da execução.
