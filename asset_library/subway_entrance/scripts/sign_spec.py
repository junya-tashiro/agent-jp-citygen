"""Blender-independent station route badge input."""
import re
COLORS={'M':'#E53935','H':'#9CA5A9','C':'#00A568','G':'#F39700','T':'#009BBF','Y':'#C5A86B','Z':'#8F76D6','N':'#00ADA9','F':'#996B49'}
def normalize_routes(routes):
    if routes is None:return []
    if not isinstance(routes,(list,tuple)) or len(routes)>6:raise ValueError('routes must contain up to 6 station codes')
    result=[]
    for item in routes:
        if isinstance(item,str):item={'code':item}
        if not isinstance(item,dict):raise ValueError('route must be a code or object')
        code=item.get('code','')
        if not isinstance(code,str) or not re.fullmatch(r'[A-Z]{1,2}[0-9]{2}',code):raise ValueError('route code must look like M11')
        letters=re.match(r'[A-Z]+',code)[0]
        color=item.get('color',COLORS.get(letters,'#356E87'))
        if not isinstance(color,str) or not re.fullmatch(r'#[0-9A-Fa-f]{6}',color):raise ValueError('route color must be #RRGGBB')
        if any(r['code']==code for r in result):raise ValueError('duplicate route code')
        result.append({'code':code,'color':color.upper()})
    return result


def parse_route_argument(value):
    """CLI form: M11=#E53935. Bare codes retain the existing defaults."""
    code,separator,color=value.partition('=')
    item={'code':code,'color':color} if separator else code
    return normalize_routes([item])[0]
