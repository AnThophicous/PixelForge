# MapSource

## Objetivo

Upscale local de imagens em Python com uma interface simples, pipeline de qualidade e backend opcional de super-resolução por IA.

## Escopo

- `upscale_app.py`: CLI, GUI Tkinter, pipeline local, tiles e backend OpenCV DNN opcional.
- `upscale_app.py`: integração opcional com Laya em `https://wire.ia.br/v1/decide`, usando metadados e fallback local.
- `requirements.txt`: Pillow obrigatório; OpenCV contrib opcional.
- `.env.example`: somente o nome da variável opcional `LAYA_KEY`.
- `tests/`: contratos do pipeline local, limites de saída e leitura segura do `.env`.
- `android/`: app PixelForge em Kotlin/Compose Material 3, fila serial, FSRCNN para imagens, Media3 Transformer para vídeos e workflow de APK.

## Decisões

- O arquivo de imagem não é enviado à API Laya; a consulta opcional usa apenas metadados.
- A integração Laya rejeita redirecionamentos, limita timeout e resposta e nunca imprime a chave.
- O modo `auto` nunca falha por falta de IA: cai para o pipeline local.
- O modo `ai` falha explicitamente se o modelo ou a dependência não existirem.
- A seleção automática usa EDSR até 2048 px na maior dimensão da saída; FSRCNN e ESPCN ficam disponíveis até 4096 px.
- A saída padrão é PNG para evitar perda adicional por JPEG.
- O APK não inclui a chave Laya; o processamento Android não envia imagens para o Laya.

## Aceite

- [x] Executar CLI com a imagem de referência e produzir saída ampliada.
- [x] Executar testes automatizados.
- [x] Abrir a GUI em modo real.
- [x] Baixar e exercitar EDSR, FSRCNN e ESPCN em imagem de teste.
- [ ] Compilar e instalar APK Android em dispositivo real.
- [ ] Verificar vídeo real no dispositivo; o código usa Media3 Transformer e precisa do build/device gate.

## Suspeitas

- `medium` — `upscale_app.py`: modelos `.pb` podem exigir um fator específico; usar uma escala diferente é rejeitado pelo OpenCV. Mitigação: usar modelo x4 com `-s 4`.
- `low` — `upscale_app.py`: os modelos foram exercitados em 32x32 e produziram saídas 128x128; imagens grandes ainda têm custo de CPU/RAM proporcional ao tile e ao modelo.
- `high` — `android/`: o host atual não tem Java, Android SDK, Gradle ou adb; a compilação depende do workflow GitHub e a instalação no Hot 50 Pro ainda não foi observada.
- `low` — `models/*.pb`: os arquivos foram baixados e verificados por tamanho e SHA-256; a inferência ainda depende de `opencv-contrib-python` instalado localmente.
- `medium` — `upscale_app.py`: a resposta live do endpoint Laya não foi chamada nesta rodada porque a chave real não é lida nem exposta durante testes. O contrato foi coberto com mock.
