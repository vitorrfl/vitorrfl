"""Gera o SVG do grafico de atividade dos ultimos 30 dias.

Le o calendario de contribuicoes pela API GraphQL do GitHub e escreve um
SVG estatico. Substitui o github-readme-activity-graph.vercel.app, que saiu
do ar de vez (HTTP 402 DEPLOYMENT_DISABLED) por estourar a cota do Vercel.

Uso: python activity_graph.py <usuario> <arquivo-de-saida>
     precisa da env var GITHUB_TOKEN
"""

import json
import os
import subprocess
import sys
from datetime import date, datetime

# Paleta gruvbox, a mesma escrita na mao nos cards do README.
BG = "#282828"
TITLE = "#fabd2f"
TEXT = "#ebdbb2"
LINE = "#fe8019"
POINT = "#fabd2f"

DIAS = 30
W, H = 1000, 300
# margens: espaco a esquerda para os rotulos do eixo Y, embaixo para as datas
ML, MR, MT, MB = 60, 30, 70, 55

MESES = ["jan", "fev", "mar", "abr", "mai", "jun",
         "jul", "ago", "set", "out", "nov", "dez"]

QUERY = """
{
  user(login: "%s") {
    contributionsCollection {
      contributionCalendar {
        weeks { contributionDays { date contributionCount } }
      }
    }
  }
}
"""


def busca_dias(usuario):
    """Retorna [(date, contagem)] dos ultimos DIAS dias."""
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        sys.exit("erro: falta a env var GITHUB_TOKEN")

    req = json.dumps({"query": QUERY % usuario}).encode()
    saida = subprocess.run(
        ["curl", "-sS", "-X", "POST",
         "-H", f"Authorization: bearer {token}",
         "-H", "Content-Type: application/json",
         "--data-binary", "@-",
         "https://api.github.com/graphql"],
        input=req, capture_output=True, check=True,
    ).stdout

    dados = json.loads(saida)
    if "errors" in dados:
        sys.exit(f"erro da API: {dados['errors']}")

    cal = dados["data"]["user"]["contributionsCollection"]["contributionCalendar"]
    dias = [d for semana in cal["weeks"] for d in semana["contributionDays"]]
    # a API devolve o ano inteiro; corta no periodo e ignora datas futuras
    hoje = date.today()
    dias = [d for d in dias
            if datetime.strptime(d["date"], "%Y-%m-%d").date() <= hoje]
    return [(datetime.strptime(d["date"], "%Y-%m-%d").date(),
             d["contributionCount"]) for d in dias[-DIAS:]]


def caminho_suave(pts, piso):
    """Curva de Bezier ligando os pontos (spline de Catmull-Rom convertida).

    Os pontos de controle sao presos em "piso" (o y de zero contribuicoes):
    solta, a spline ultrapassa o ponto mais baixo entre dois picos e desenha
    a curva abaixo da linha do zero, sugerindo atividade negativa.
    """
    if len(pts) < 2:
        return ""
    d = f"M {pts[0][0]:.1f} {pts[0][1]:.1f}"
    for i in range(len(pts) - 1):
        x0, y0 = pts[i - 1] if i else pts[0]
        x1, y1 = pts[i]
        x2, y2 = pts[i + 1]
        x3, y3 = pts[i + 2] if i + 2 < len(pts) else pts[-1]
        # tensao 6 = suavizacao equivalente ao "radius" do grafico original
        c1x, c1y = x1 + (x2 - x0) / 6, y1 + (y2 - y0) / 6
        c2x, c2y = x2 - (x3 - x1) / 6, y2 - (y3 - y1) / 6
        # y cresce para baixo no SVG, entao "nao passar do zero" e min(y, piso)
        c1y, c2y = min(c1y, piso), min(c2y, piso)
        d += (f" C {c1x:.1f} {c1y:.1f}, {c2x:.1f} {c2y:.1f},"
              f" {x2:.1f} {y2:.1f}")
    return d


def monta_svg(usuario, dias):
    contagens = [c for _, c in dias]
    total = sum(contagens)
    topo = max(max(contagens), 1)
    # arredonda a escala pra cima, pra linha nao encostar no teto
    passo = max(1, -(-topo // 4))
    topo_escala = passo * 4

    larg = W - ML - MR
    alt = H - MT - MB
    dx = larg / max(len(dias) - 1, 1)

    pts = [(ML + i * dx, MT + alt - (c / topo_escala) * alt)
           for i, (_, c) in enumerate(dias)]

    p = []
    p.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
        f'viewBox="0 0 {W} {H}" font-family="Segoe UI, Ubuntu, sans-serif">'
    )
    p.append(
        f'<defs><linearGradient id="area" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0%" stop-color="{LINE}" stop-opacity="0.55"/>'
        f'<stop offset="100%" stop-color="{LINE}" stop-opacity="0.02"/>'
        f"</linearGradient></defs>"
    )
    p.append(f'<rect width="{W}" height="{H}" rx="16" fill="{BG}"/>')

    p.append(
        f'<text x="{ML}" y="38" fill="{TITLE}" font-size="20" '
        f'font-weight="600">Gráfico de atividade — últimos {DIAS} dias</text>'
    )
    p.append(
        f'<text x="{ML}" y="58" fill="{TEXT}" font-size="13" '
        f'opacity="0.75">{usuario} · {total} contribuições no período</text>'
    )

    # grade horizontal + rotulos do eixo Y
    for i in range(5):
        v = topo_escala - passo * i
        y = MT + (alt / 4) * i
        p.append(
            f'<line x1="{ML}" y1="{y:.1f}" x2="{W - MR}" y2="{y:.1f}" '
            f'stroke="{TEXT}" stroke-opacity="0.12" stroke-width="1"/>'
        )
        p.append(
            f'<text x="{ML - 12}" y="{y + 4:.1f}" fill="{TEXT}" '
            f'font-size="11" opacity="0.6" text-anchor="end">{v}</text>'
        )

    base = MT + alt
    linha = caminho_suave(pts, base)
    p.append(
        f'<path d="{linha} L {pts[-1][0]:.1f} {base} L {pts[0][0]:.1f} {base} Z" '
        f'fill="url(#area)"/>'
    )
    p.append(
        f'<path d="{linha}" fill="none" stroke="{LINE}" stroke-width="2.5" '
        f'stroke-linecap="round" stroke-linejoin="round"/>'
    )

    for (x, y), (_, c) in zip(pts, dias):
        # ponto cheio so nos dias com atividade, pra nao poluir a linha de base
        if c:
            p.append(
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.5" fill="{POINT}" '
                f'stroke="{BG}" stroke-width="1.5"/>'
            )

    # rotulos de data espacados, pra caber sem sobrepor
    salto = max(1, len(dias) // 8)
    for i, (dia, _) in enumerate(dias):
        if i % salto == 0 or i == len(dias) - 1:
            p.append(
                f'<text x="{pts[i][0]:.1f}" y="{base + 24}" fill="{TEXT}" '
                f'font-size="11" opacity="0.6" text-anchor="middle">'
                f"{dia.day} {MESES[dia.month - 1]}</text>"
            )

    p.append("</svg>")
    return "\n".join(p)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("uso: activity_graph.py <usuario> <saida.svg>")
    usuario, saida = sys.argv[1], sys.argv[2]
    svg = monta_svg(usuario, busca_dias(usuario))
    os.makedirs(os.path.dirname(saida) or ".", exist_ok=True)
    with open(saida, "w", encoding="utf-8") as f:
        f.write(svg)
    print(f"gerado: {saida}")
