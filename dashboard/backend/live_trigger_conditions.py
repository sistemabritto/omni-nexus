"""Bounded declarative conditions. No expressions, imports, regex or eval."""
import fnmatch
import re
import math

OPS={'eq','ne','in','contains','gt','gte','lt','lte','exists','glob'}


def validate(tree):
    count=0
    def visit(node,depth=0):
        nonlocal count
        count+=1
        if count>64 or depth>6 or not isinstance(node,dict):raise ValueError('invalid_condition')
        if set(node) in ({'all'},{'any'}):
            children=next(iter(node.values()))
            if not isinstance(children,list) or not 1<=len(children)<=16:raise ValueError('invalid_condition')
            for child in children:visit(child,depth+1)
        elif set(node)=={'not'}:visit(node['not'],depth+1)
        else:
            if set(node)!={'field','op','value'} or node['op'] not in OPS or not isinstance(node['field'],str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+){0,5}',node['field']):raise ValueError('invalid_condition')
            value=node['value']
            if not (value is None or type(value) in (bool,int,float,str,list)):raise ValueError('invalid_condition')
            if isinstance(value,str) and len(value)>500:raise ValueError('invalid_condition')
            if isinstance(value,list) and (len(value)>30 or any(type(v) not in (str,int,float,bool) for v in value)):raise ValueError('invalid_condition')
            if any(type(v) is float and not math.isfinite(v) for v in (value if isinstance(value,list) else [value])):raise ValueError('invalid_condition')
            if node['op']=='exists' and type(value) is not bool:raise ValueError('invalid_condition')
            if node['op']=='in' and not isinstance(value,list):raise ValueError('invalid_condition')
            if node['op']=='glob' and not isinstance(value,str):raise ValueError('invalid_condition')
            if node['op'] in ('gt','gte','lt','lte') and type(value) not in (int,float):raise ValueError('invalid_condition')
    visit(tree)


def matches(event,tree):
    validate(tree)
    def evaluate(node):
        if 'all' in node:return all(evaluate(child) for child in node['all'])
        if 'any' in node:return any(evaluate(child) for child in node['any'])
        if 'not' in node:return not evaluate(node['not'])
        actual=event;present=True
        for part in node['field'].split('.'):
            if not isinstance(actual,dict) or part not in actual:present=False;actual=None;break
            actual=actual[part]
        op,expected=node['op'],node['value']
        if op=='exists':return present==expected
        if not present:return False
        if op=='eq':return type(actual) is type(expected) and actual==expected
        if op=='ne':return type(actual) is not type(expected) or actual!=expected
        if op=='in':return any(type(actual) is type(v) and actual==v for v in expected)
        if op=='contains':return isinstance(actual,(str,list)) and isinstance(expected,str) and expected in actual
        if op=='glob':return isinstance(actual,str) and fnmatch.fnmatchcase(actual,expected)
        if type(actual) not in (int,float):return False
        return {'gt':lambda:actual>expected,'gte':lambda:actual>=expected,
                'lt':lambda:actual<expected,'lte':lambda:actual<=expected}[op]()
    return evaluate(tree)
