import io
from fastapi.responses import Response

def generate_svg_card(stats: dict) -> str:
    # Use existing house colors
    return f'''
    <svg width="600" height="315" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stop-color="#07090b"/>
          <stop offset="100%" stop-color="#1e293b"/>
        </linearGradient>
      </defs>
      <rect width="600" height="315" fill="url(#g)"/>
      <text x="50" y="80" font-family="monospace" font-size="24" fill="#22d3ee">EdgeLog Stats</text>
      <text x="50" y="140" font-family="monospace" font-size="48" fill="#eafff2">Expectancy: {stats.get('expectancy_r', 0)}R</text>
      <text x="50" y="190" font-family="monospace" font-size="24" fill="#a78bfa">Win Rate: {stats.get('win_rate', 0)}%</text>
      <text x="50" y="230" font-family="monospace" font-size="24" fill="#3ddc84">Profit Factor: {stats.get('profit_factor', 0)}</text>
    </svg>
    '''

@app.get("/api/share/card.svg")
def share_card():
    stats = stats() # Recalculate
    svg = generate_svg_card(stats)
    return Response(content=svg, media_type="image/svg+xml")
