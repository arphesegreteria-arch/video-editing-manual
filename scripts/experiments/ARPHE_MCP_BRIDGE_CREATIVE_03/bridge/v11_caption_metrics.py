"""Measured Satoshi Medium caption widths for the approved V11 font/render scale.

Values are normalized against 1080 px and were measured on PC_PERSONALE with
the installed Satoshi Medium face at the effective 42 px raster scale for
Fusion Text+ Size 0.0646.  Layout derives from the measured glyph widths;
it never uses a character-count minimum width.
"""
from __future__ import annotations

_WIDTH = {
 'NON':.10287,'ESISTE':.13904,'UN':.07083,'SOLO':.11921,'TRATTAMENTO':.30059,'GIUSTO':.1595,
 'PER':.08755,'TUTTI,':.13072,'QUELLO':.16883,'TE,':.06986,'RIDRATARE,':.24116,
 'ILLUMINARE,':.25563,'RESTITUIRE':.23004,'TONO':.1271,'E':.0363,'QUALITÀ':.17972,
 'ALLA':.10785,'PELLE,':.13756,'SCEGLIAMO':.2435,'TRA':.08821,'PROTOCOLLI':.26236,
 'PRODOTTI':.2111,'DIVERSI,':.17377,'IN':.05306,'BASE':.11151,'ALLE':.10466,'TUE':.08728,
 'ESIGENZE,':.21118,'DOPO':.12916,'UNA':.09735,'VALUTAZIONE':.2769,'ACCURATA':.22922,
 'COSTRUIAMO':.2769,'IL':.04458,'PERCORSO':.22884,'PIÙ':.07717,'ADATTO':.17109,'A':.03949,
}

def layout_width(word: str) -> float:
    measured = _WIDTH[word]
    # Eight percent side breathing room plus the 0.012 normalized raster guard.
    return round(measured * 1.08 + .012, 5)

def phrase_word_slots_measured(words: list[str]) -> list[tuple[float,float,float,float]]:
    widths=[layout_width(word) for word in words]; rows=[[]];used=0.0
    for index,width in enumerate(widths):
        extra=width if not rows[-1] else width+.025
        if rows[-1] and used+extra>.66:
            rows.append([]);used=0.0;extra=width
        rows[-1].append(index);used+=extra
    ys=[.75,.69] if len(rows)==2 else [.72]; result=[None]*len(words)
    for row_index,row in enumerate(rows):
        total=sum(widths[i] for i in row)+.025*(len(row)-1);cursor=.5-total/2
        for index in row:
            result[index]=(cursor+widths[index]/2,ys[row_index],float(row_index),widths[index]);cursor+=widths[index]+.025
    return result
