"""QR code minimal (norme ISO 18004), pour afficher l'adresse de la page « photo par téléphone ».

Mode octet, correction d'erreurs M, versions 1 à 6 (jusqu'à 106 caractères) : assez pour une
adresse locale du type ``http://192.168.1.20:52345/jeton``. Écrit ici pour éviter une dépendance.
Construction calquée sur la bibliothèque de référence de Nayuki (``modules[y][x]``).
"""

#: Par version : (nombre total d'octets, octets de correction par bloc, nombre de blocs), niveau M.
_VERSIONS = {1: (26, 10, 1), 2: (44, 16, 1), 3: (70, 26, 1), 4: (100, 18, 2), 5: (134, 24, 2), 6: (172, 16, 4)}
_ALIGN = {1: [], 2: [6, 18], 3: [6, 22], 4: [6, 26], 5: [6, 30], 6: [6, 34]}


def _mul(x, y):
    """Produit dans GF(256), polynôme 0x11D."""
    z = 0
    for i in range(7, -1, -1):
        z = (z << 1) ^ ((z >> 7) * 0x11D)
        z ^= ((y >> i) & 1) * x
    return z


def rs_ecc(data, degree):
    """Octets de correction Reed-Solomon de ``data``."""
    div = [0] * (degree - 1) + [1]
    root = 1
    for _ in range(degree):
        for j in range(degree):
            div[j] = _mul(div[j], root)
            if j + 1 < degree:
                div[j] ^= div[j + 1]
        root = _mul(root, 2)
    res = [0] * degree
    for b in data:
        factor = b ^ res.pop(0)
        res.append(0)
        for i, coef in enumerate(div):
            res[i] ^= _mul(coef, factor)
    return res


def format_bits(mask):
    """15 bits d'information de format pour le niveau M et le masque ``mask``."""
    data = mask  # niveau M = 00
    rem = data
    for _ in range(10):
        rem = (rem << 1) ^ ((rem >> 9) * 0x537)
    return (data << 10 | rem) ^ 0x5412


def encode(text):
    """Matrice du QR code de ``text`` : liste de lignes de booléens (``True`` = module noir)."""
    raw = text.encode("utf-8")
    version = next((v for v, (total, ecc, blocks) in _VERSIONS.items() if len(raw) <= total - ecc * blocks - 2), None)
    if version is None:
        raise ValueError("Texte trop long pour le QR code")
    total, ecc_len, nblocks = _VERSIONS[version]
    capacity = total - ecc_len * nblocks

    # Données : mode octet (0100), longueur sur 8 bits, octets, fin, remplissage.
    bits = "0100" + f"{len(raw):08b}" + "".join(f"{b:08b}" for b in raw)
    bits += "0" * min(4, capacity * 8 - len(bits))
    bits += "0" * (-len(bits) % 8)
    data = [int(bits[i:i + 8], 2) for i in range(0, len(bits), 8)]
    data += [0xEC, 0x11] * ((capacity - len(data)) // 2) + [0xEC] * ((capacity - len(data)) % 2)

    # Blocs (les derniers ont un octet de plus), correction, entrelacement.
    short = capacity // nblocks
    nshort = nblocks - capacity % nblocks
    blocks, pos = [], 0
    for i in range(nblocks):
        size = short + (i >= nshort)
        blocks.append(data[pos:pos + size])
        pos += size
    eccs = [rs_ecc(b, ecc_len) for b in blocks]
    codewords = [b[i] for i in range(short + 1) for b in blocks if i < len(b)]
    codewords += [e[i] for i in range(ecc_len) for e in eccs]

    n = 17 + 4 * version
    m = [[False] * n for _ in range(n)]
    fn = [[False] * n for _ in range(n)]

    def put(x, y, dark):
        m[y][x], fn[y][x] = dark, True

    for i in range(n):  # lignes de synchronisation
        put(6, i, i % 2 == 0)
        put(i, 6, i % 2 == 0)
    for cx, cy in ((3, 3), (n - 4, 3), (3, n - 4)):  # repères de position et séparateurs
        for dy in range(-4, 5):
            for dx in range(-4, 5):
                if 0 <= cx + dx < n and 0 <= cy + dy < n:
                    put(cx + dx, cy + dy, max(abs(dx), abs(dy)) not in (2, 4))
    al = _ALIGN[version]
    for cx in al:  # repères d'alignement (sauf sur les repères de position)
        for cy in al:
            if (cx, cy) not in ((al[0], al[0]), (al[0], al[-1]), (al[-1], al[0])):
                for dy in range(-2, 3):
                    for dx in range(-2, 3):
                        put(cx + dx, cy + dy, max(abs(dx), abs(dy)) != 1)
    mask = 0  # shortcut: masque fixe sans calcul de pénalité, lisible par tout lecteur ; à affiner si un téléphone peine à lire
    fmt = format_bits(mask)
    bit = lambda i: (fmt >> i) & 1 == 1
    for i in range(6):
        put(8, i, bit(i))
    put(8, 7, bit(6))
    put(8, 8, bit(7))
    put(7, 8, bit(8))
    for i in range(9, 15):
        put(14 - i, 8, bit(i))
    for i in range(8):
        put(n - 1 - i, 8, bit(i))
    for i in range(8, 15):
        put(8, n - 15 + i, bit(i))
    put(8, n - 8, True)  # module toujours noir

    # Placement en zigzag, colonnes par deux de droite à gauche, puis masque 0 ((x + y) pair).
    i = 0
    right = n - 1
    while right >= 1:
        if right == 6:
            right = 5
        for vert in range(n):
            for j in range(2):
                x = right - j
                y = n - 1 - vert if (right + 1) & 2 == 0 else vert
                if not fn[y][x]:
                    if i < len(codewords) * 8:
                        m[y][x] = (codewords[i >> 3] >> (7 - (i & 7))) & 1 == 1
                        i += 1
                    m[y][x] ^= (x + y) % 2 == 0
        right -= 2
    return m


def svg(text, scale=8):
    """QR code de ``text`` en image SVG (noir sur blanc, marge de 4 modules)."""
    m = encode(text)
    size = (len(m) + 8) * scale
    rects = "".join(f'<rect x="{(x + 4) * scale}" y="{(y + 4) * scale}" width="{scale}" height="{scale}"/>'
                    for y, row in enumerate(m) for x, dark in enumerate(row) if dark)
    # Noir sur blanc imposé, quel que soit le thème : les lecteurs de QR code l'exigent.
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 {size} {size}">'
            f'<rect width="{size}" height="{size}" fill="#fff"/><g fill="#000">{rects}</g></svg>')
