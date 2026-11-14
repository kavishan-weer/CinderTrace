"""Render the observatory's computed brief snapshot as one local, vector PDF page.

Statistics come from the same browser analytics functions as the visible charts.
This module validates the bounded rendering payload; it makes no remote requests.
"""
import math
import re
import unicodedata
from html import escape


def validate_brief(value):
    if not isinstance(value, dict) or value.get('version') != 1:
        raise ValueError('Invalid brief snapshot. Refresh the app and retry.')
    for key in ['area', 'filters', 'snapshot', 'window', 'spatial', 'selected',
                'selected_label', 'generated_utc', 'year_basis', 'status', 'coverage', 'sources']:
        if not isinstance(value.get(key), str) or not 0 < len(value[key]) <= 650:
            raise ValueError(f'Invalid brief {key}.')
    if not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])', value['selected']):
        raise ValueError('Invalid brief month.')
    for key, minimum, maximum in [('findings', 1, 3), ('limits', 1, 5)]:
        items = value.get(key)
        if not isinstance(items, list) or not minimum <= len(items) <= maximum or any(not isinstance(t, str) or len(t) > 700 for t in items):
            raise ValueError(f'Invalid brief {key}.')
    cards = value.get('cards')
    if not isinstance(cards, list) or len(cards) != 3 or any(not isinstance(c, dict) or any(not isinstance(c.get(k), str) or len(c[k]) > 120 for k in ['label', 'value', 'note']) for c in cards):
        raise ValueError('Invalid brief summary cards.')

    def amount(v):
        return v is None or (type(v) in [int, float] and math.isfinite(v) and v >= 0)

    calendar = value.get('calendar')
    if not isinstance(calendar, list) or not 1 <= len(calendar) <= 8:
        raise ValueError('Invalid brief calendar.')
    for row in calendar:
        if not isinstance(row, dict) or not isinstance(row.get('label'), str) or len(row['label']) > 12 or not isinstance(row.get('months'), list) or len(row['months']) != 12:
            raise ValueError('Invalid brief calendar year.')
        for cell in row['months']:
            if not isinstance(cell, dict) or not isinstance(cell.get('month'), str) or not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])', cell['month']) or not amount(cell.get('value')) or any(type(cell.get(k)) is not bool for k in ['eligible', 'provisional']):
                raise ValueError('Invalid brief calendar month.')
    profile = value.get('profile')
    if profile is not None:
        if not isinstance(profile, dict) or not isinstance(profile.get('label'), str) or len(profile['label']) > 12:
            raise ValueError('Invalid brief season.')
        values, keys = profile.get('values'), profile.get('keys')
        if not isinstance(values, list) or len(values) != 12 or any(v is None or not amount(v) for v in values) or not sum(values) > 0:
            raise ValueError('Invalid brief season activity.')
        if not isinstance(keys, list) or len(keys) != 12 or any(not isinstance(k, str) or not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])', k) for k in keys):
            raise ValueError('Invalid brief season months.')
        if any(type(profile.get(k)) is not int for k in ['onset', 'end', 'duration']) or not 0 <= profile['onset'] <= profile['end'] <= 11 or profile['duration'] != profile['end'] - profile['onset'] + 1:
            raise ValueError('Invalid brief season timing.')
        peaks = profile.get('peaks')
        if not isinstance(peaks, list) or not peaks or len(peaks) > 12 or any(type(p) is not int or not 0 <= p <= 11 for p in peaks):
            raise ValueError('Invalid brief season peaks.')
    return value


def ascii_text(value):
    text = str(value).replace('–', '-').replace('—', '-').replace('→', 'to').replace('↗', '').replace('·', '/').replace('²', '2').replace('≥', '>=').replace('−', '-')
    return unicodedata.normalize('NFKD', text).encode('ascii', 'replace').decode('ascii')


def render_brief(value, output):
    brief = validate_brief(value)
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Flowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    ink, muted, paper = '#243c30', '#53684c', '#f5f6ef'
    width = A4[0] - 64
    style = ParagraphStyle('body', fontName='Helvetica', fontSize=8.2, leading=11, textColor=colors.HexColor(ink))
    small = ParagraphStyle('small', parent=style, fontSize=7.2, leading=9.5, textColor=colors.HexColor(muted))
    title = ParagraphStyle('title', parent=style, fontName='Helvetica-Bold', fontSize=25, leading=29)
    area_style = ParagraphStyle('area', parent=style, fontSize=11, leading=14)
    eyebrow = ParagraphStyle('eyebrow', parent=small, fontName='Helvetica-Bold', fontSize=7, leading=10, spaceAfter=5)
    def p(text, custom=style):
        return Paragraph(escape(ascii_text(text)), custom)

    class Charts(Flowable):
        def __init__(self):
            super().__init__()
            self.width, self.height = width, 188

        def draw(self):
            c = self.canv
            def text(x, y, value, size=7, color=muted, bold=False):
                c.setFillColor(colors.HexColor(color)); c.setFont('Helvetica-Bold' if bold else 'Helvetica', size)
                c.drawString(x, y, ascii_text(value))
            left_w, right_x, right_w = 288, 312, width - 312
            text(0, 176, 'BURNING CALENDAR', 8, ink, True)
            text(0, 164, 'Latest up to 8 starting years / log color scale', 6.8)
            all_values = [cell['value'] for row in brief['calendar'] for cell in row['months'] if cell['value'] is not None]
            maximum = math.log1p(max(all_values, default=0)) or 1
            names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
            months = [names[int(cell['month'][5:]) - 1] for cell in brief['calendar'][0]['months']]
            x0, step, row_h = 39, (left_w - 39) / 12, 13
            for i, name in enumerate(months): text(x0 + i * step + 1, 149, name, 6)
            for j, row in enumerate(reversed(brief['calendar'])):
                y = 132 - j * row_h
                text(0, y + 3, row['label'], 6.5)
                for i, cell in enumerate(row['months']):
                    x, v = x0 + i * step, cell['value']
                    t = math.log1p(v) / maximum if v is not None else None
                    rgb = (0.84, 0.86, 0.82) if t is None else tuple(a + (b-a)*t for a, b in zip((.12,.25,.25),(.91,.89,.49)))
                    c.setFillColor(colors.Color(*rgb)); c.rect(x, y, step-2, 10, fill=1, stroke=0)
                    if cell['provisional']:
                        c.saveState(); clip = c.beginPath(); clip.rect(x,y,step-2,10); c.clipPath(clip, stroke=0)
                        c.setStrokeColor(colors.HexColor('#f5f6ef')); c.setLineWidth(.7)
                        for k in range(-10, 30, 5): c.line(x+k,y,x+k+10,y+10)
                        c.restoreState()
                    if cell['month'] == brief['selected']:
                        c.setStrokeColor(colors.HexColor('#c7613c')); c.setLineWidth(1.2); c.rect(x-.5,y-.5,step-1,11,fill=0,stroke=1)
            for i in range(60):
                t = i/59; c.setFillColor(colors.Color(*[a+(b-a)*t for a,b in zip((.12,.25,.25),(.91,.89,.49))])); c.rect(i*1.3,11,1.4,5,stroke=0,fill=1)
            text(84, 10, 'Low > high / gray: missing / hatch: provisional', 6.1)
            text(0, 0, 'Orange outline: selected month / units: cell-days', 6.5)

            profile = brief['profile']
            text(right_x, 176, 'LATEST COMPLETE ACTIVE SEASON', 7.5, ink, True)
            if profile is None:
                text(right_x, 148, 'No eligible season in this window.', 8)
                text(right_x, 131, 'Needs all 12 months and positive activity.', 6.8)
                return
            text(right_x, 163, f"{profile['label']} / monthly share of annual activity", 7)
            values = profile['values']; total = sum(values)
            chart_y, chart_h, bar_w = 48, 96, right_w/12
            for pct in [10, 90]:
                y = chart_y+chart_h*pct/100
                c.setStrokeColor(colors.HexColor('#adbba0')); c.setDash(2,3); c.setLineWidth(.5); c.line(right_x,y,right_x+right_w,y); c.setDash()
                text(right_x+right_w-17,y+3,f'{pct}%',6)
            path = c.beginPath(); path.moveTo(right_x,chart_y); cumulative=0
            for i, v in enumerate(values):
                height=chart_h*v/total
                c.setFillColor(colors.HexColor('#c7613c' if i in profile['peaks'] else '#799e77' if profile['onset']<=i<=profile['end'] else '#cbd6bd'))
                c.roundRect(right_x+i*bar_w+2, chart_y,bar_w-4,height,1,fill=1,stroke=0)
                cumulative+=v; path.lineTo(right_x+(i+1)*bar_w,chart_y+chart_h*cumulative/total)
                text(right_x+i*bar_w+1,chart_y-11,names[int(profile['keys'][i][5:])-1],6.3)
            c.setStrokeColor(colors.HexColor(ink)); c.setLineWidth(1.5); c.drawPath(path)
            text(right_x, 20, 'Bars: monthly share / line: cumulative share',6.7)
            text(right_x, 7, 'Orange: peak / season window: 10%-90%',6.7)
            text(right_x, -5, f"Duration: {profile['duration']} months, inclusive",6.7)

    story = [p('EMBERLINE / LOCAL FIRE OBSERVATORY', eyebrow), p('Situation brief.', title), Spacer(1, 5), p(brief['area'], area_style), Spacer(1, 5), p(brief['filters'], small), p(brief['spatial'], small), Spacer(1, 6), p(f"SELECTED MONTH: {brief['selected_label']} / {brief['status']}   |   HISTORY: {brief['window']}", eyebrow)]
    card_cells = []
    for card in brief['cards']:
        val_style = ParagraphStyle('value', parent=style, fontName='Helvetica-Bold', fontSize=20 if len(card['value']) < 14 else 14, leading=25)
        card_cells.append([p(card['label'],small), Spacer(1,3), p(card['value'],val_style), p(card['note'],small)])
    cards = Table([card_cells], colWidths=[width/3]*3)
    cards.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),colors.HexColor('#e7eddd')),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),10),('RIGHTPADDING',(0,0),(-1,-1),9),('TOPPADDING',(0,0),(-1,-1),10),('BOTTOMPADDING',(0,0),(-1,-1),10)]))
    story += [cards, Spacer(1,13), p('KEY FINDINGS / CALCULATED FROM THIS SELECTION',eyebrow)]
    for i, finding in enumerate(brief['findings'],1):
        story += [p(f'{i:02d}  {finding}'), Spacer(1,5)]
    story += [Spacer(1,7), Charts(), Spacer(1,10), p(brief['coverage'],small), Spacer(1,12), p('UNCERTAINTY / WHAT THIS PAGE CANNOT ESTABLISH',eyebrow)]
    for line in brief['limits']:
        story += [p(line,small),Spacer(1,4)]
    story += [Spacer(1,6),p('SOURCE & PROVENANCE',eyebrow),p(brief['sources'],small),p(f"Archive snapshot: {brief['snapshot']} / Generated UTC: {brief['generated_utc']}",small)]

    def page(c, doc):
        if doc.page != 1:
            raise ValueError('The brief text exceeds one page. Choose a shorter area label or fewer filters.')
        c.saveState();c.setFillColor(colors.HexColor(paper));c.rect(0,0,*A4,fill=1,stroke=0)
        c.setStrokeColor(colors.HexColor('#cad4bd'));c.line(32,27,A4[0]-32,27)
        c.setFillColor(colors.HexColor(muted));c.setFont('Helvetica',6.5)
        c.drawString(32,16,'EMBERLINE / Historical evidence for review / Not an operational warning or forecast')
        c.drawRightString(A4[0]-32,16,'1 / 1');c.restoreState()

    doc = SimpleDocTemplate(str(output),pagesize=A4,rightMargin=32,leftMargin=32,topMargin=29,bottomMargin=36,title=ascii_text(f"EMBERLINE situation brief - {brief['area']} - {brief['selected']}"),author='EMBERLINE',pageCompression=1)
    doc.build(story,onFirstPage=page,onLaterPages=page)
    if doc.page != 1:
        raise ValueError('The brief must contain exactly one page.')
    return 1
