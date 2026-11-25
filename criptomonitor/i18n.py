"""UI strings. English is the default; Portuguese (pt-BR) is available with the L key."""

LANGS = ("en", "pt")

STRINGS = {
    "market": ("Market", "Mercado"),
    "search": ("Search", "Buscar"),
    "by_symbol": ("by symbol", "por abreviação"),
    "chart": ("Chart", "Gráfico"),
    "theme": ("Theme", "Tema"),
    "help": ("Help", "Ajuda"),
    "open": ("Open", "Abrir"),
    "move": ("Move", "Mover"),
    "delete": ("Delete", "Apagar"),
    "back": ("Back", "Voltar"),
    "period": ("Period", "Período"),
    "cursor": ("Cursor", "Cursor"),
    "coin": ("Coin", "Moeda"),
    "pin": ("Pin", "Fixar"),
    "unpin": ("Unpin", "Desafixar"),
    "high": ("High", "Máx"),
    "low": ("Low", "Mín"),
    "vol24": ("Vol 24h", "Vol 24h"),
    "updated": ("updated {t}", "atualizado {t}"),
    "popular": ("Popular", "Populares"),
    "type_symbol": ("Type a symbol, e.g. PEPE", "Digite o símbolo, ex: PEPE"),
    "loading_list": ("Loading list…", "Carregando lista…"),
    "searching": ("Searching…", "Buscando…"),
    "not_found": ("Nothing found for “{q}”", "Nada encontrado para “{q}”"),
    "loading_chart": ("Loading chart…", "Carregando gráfico…"),
    "chart_failed": ("Could not load chart", "Não foi possível carregar"),
    "press_r": ("Press R to retry", "R para tentar de novo"),
    "empty_title": ("No coins on the dashboard", "Nenhuma moeda no painel"),
    "empty_hint": ("Search with S, pin with P", "Busque com S e fixe com P"),
    "refreshing": ("Refreshing…", "Atualizando…"),
    "save_failed": ("Could not save settings", "Não foi possível salvar preferências"),
    "settings_corrupt": ("Settings were corrupt; using defaults", "Preferências corrompidas; usando padrão"),
    "board_full": ("Dashboard full (max 12)", "Painel cheio (máx. 12)"),
    "pinned": ("{s} pinned to dashboard", "{s} fixada no painel"),
    "unpinned": ("{s} removed from dashboard", "{s} removida do painel"),
    "shot_saved": ("Screenshot saved", "Captura salva"),
    "shot_failed": ("Screenshot failed", "Falha ao salvar captura"),
    "currency_usd": ("Currency: US Dollar (US$)", "Moeda: Dólar (US$)"),
    "currency_brl": ("Currency: Brazilian Real (R$)", "Moeda: Real (R$)"),
    "language": ("Language: English", "Idioma: Português"),
    "shortcuts": ("Shortcuts", "Atalhos"),
    "any_key": ("any key closes", "qualquer tecla fecha"),
    "h_move": ("move (Fn+F/X in search)", "mover (Fn+F/X na busca)"),
    "h_enter": ("open chart", "abrir gráfico"),
    "h_search": ("search coin by symbol", "buscar moeda por abreviação"),
    "h_period": ("period 1H 24H 7D 30D 1Y", "período 1H 24H 7D 30D 1A"),
    "h_cursor": ("chart cursor", "cursor no gráfico"),
    "h_pin": ("pin/unpin on dashboard", "fixar/remover do painel"),
    "h_mtr": ("currency · theme · lang · refresh", "moeda · tema · idioma · atualizar"),
    "h_esc": ("back  (hold: quit)", "voltar  (segurar: sair)"),
    # network errors (keys produced by market._friendly)
    "err_429": ("API rate limit hit; waiting", "Limite da API atingido; aguardando"),
    "err_451": ("API unavailable in this region", "API indisponível nesta região"),
    "err_403": ("Access denied by the API", "Acesso negado pela API"),
    "err_http": ("Server responded {a}", "Servidor respondeu {a}"),
    "err_timeout": ("Request timed out", "Tempo esgotado"),
    "err_offline": ("No connection", "Sem conexão"),
    "err_network": ("Network error", "Falha de rede"),
    "err_bad_reply": ("Unexpected server reply", "Resposta inesperada do servidor"),
}

PERIOD_LABELS = {"1A": ("1Y", "1A")}


def tr(lang, key, **kw):
    """Translate `key`. A key may carry an argument as 'key:arg' (used for HTTP codes)."""
    arg = None
    if ":" in key:
        key, arg = key.split(":", 1)
    pair = STRINGS.get(key)
    if not pair:
        return key
    text = pair[1] if lang == "pt" else pair[0]
    if arg is not None:
        kw.setdefault("a", arg)
    return text.format(**kw) if kw else text


def period_label(lang, key):
    pair = PERIOD_LABELS.get(key)
    if not pair:
        return key
    return pair[1] if lang == "pt" else pair[0]
