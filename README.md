# Claude Monitor

Um overlay leve para Windows que monitora em tempo real o uso do Claude AI e o status das sessões ativas do Claude Code e Claude Desktop.
*Projeto feito com Claude Code*

## Como funciona?

O programa roda em segundo plano com um ícone na bandeja do sistema. Um pequeno painel é exibido no canto superior esquerdo da tela com um ponto colorido e uma barra de progresso indicando o uso do limite do Claude.

Ao passar o mouse sobre o painel, ele se expande e mostra:

- Todas as sessões ativas (Claude Code no VSCode, CLI, Claude Desktop/Cowork);
- O status de cada sessão com um ponto colorido;
- A porcentagem de uso atual do limite de 5 horas;
- O tempo restante até o reset do limite.

### Status das sessões.

- Verde — Ocioso;
- Amarelo — Trabalhando;
- Vermelho — Aguardando input.

## Como usar?

1. Instale as dependências:
   ```bash
   pip install -r requirements.txt
   ```
2. Execute o programa:
   ```bash
   python main.pyw
   ```
   Ou simplesmente clique duas vezes em `run.bat`.

3. O ícone aparecerá na bandeja do sistema. Use **Show / Hide** para mostrar ou ocultar o overlay, e **Quit** para encerrar.

> **Nota:** O monitor lê o token de autenticação do arquivo `~/.claude/.credentials.json` gerado pelo Claude Code. Certifique-se de estar autenticado.

## Tecnologias utilizadas.

- Python 3.11+;
- Tkinter — interface gráfica do overlay;
- pystray — ícone na bandeja do sistema;
- Pillow — geração do ícone colorido;
- psutil — detecção de processos ativos;
- requests — consumo da API de uso do Claude.

## Requisitos.

- Windows 10/11;
- Python 3.11 ou superior;
- Claude Code instalado e autenticado.
