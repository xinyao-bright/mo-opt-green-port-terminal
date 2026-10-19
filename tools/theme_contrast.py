"""Check theme color-token pairs against the 4.5:1 normal-text contrast target.

This is a static token audit, not a browser/computed-style accessibility audit.
Hex, rgb(a), simple var references and alpha compositing are supported.
Usage: python tools/theme_contrast.py [--all] [--css PATH]
"""
from pathlib import Path
import argparse
import re
import sys

ROOT = Path(__file__).resolve().parents[1]


def read_themes(css):
    css = re.sub(r'/\*.*?\*/', '', css, flags=re.S)
    base, overrides = {}, {}
    for selectors, body in re.findall(r'([^{}]+)\{([^{}]*)\}', css):
        declarations = dict(re.findall(r'(--[\w-]+)\s*:\s*([^;{}]+)', body))
        selectors = [value.strip() for value in selectors.split(',')]
        if ':root' in selectors:
            base.update(declarations)
        for selector in selectors:
            matched = re.fullmatch(r'\[data-theme\s*=\s*[\"\x27]?([\w-]+)[\"\x27]?\]', selector)
            if matched:
                overrides.setdefault(matched[1], {}).update(declarations)
    if not overrides:
        raise ValueError('No root theme selectors found')
    return {name: base | values for name, values in overrides.items()}


def color(value, tokens, seen=()):
    value = value.strip().replace('!important', '').strip().lower()
    if value.startswith('--'):
        if value in seen:
            raise ValueError('Circular token reference: ' + value)
        if value not in tokens:
            raise ValueError('Missing token: ' + value)
        return color(tokens[value], tokens, seen + (value,))
    variable = re.fullmatch(r'var\(\s*(--[\w-]+)\s*(?:,\s*(.+))?\)', value)
    if variable:
        return color(variable[1] if variable[1] in tokens else variable[2] or variable[1], tokens, seen)
    value = {'white': '#ffffff', 'black': '#000000', 'transparent': '#00000000'}.get(value, value)
    if re.fullmatch(r'#[0-9a-f]{3,8}', value):
        digits = value[1:]
        if len(digits) in (3, 4):
            digits = ''.join(char * 2 for char in digits)
        if len(digits) == 6:
            digits += 'ff'
        if len(digits) != 8:
            raise ValueError('Unsupported hex color: ' + value)
        return tuple(int(digits[index:index+2], 16) / 255 for index in range(0, 8, 2))
    rgb = re.fullmatch(r'rgba?\(([^)]+)\)', value)
    if rgb:
        parts = re.split(r'\s*[,/]\s*|\s+', rgb[1].strip())
        if len(parts) not in (3, 4):
            raise ValueError('Unsupported RGB color: ' + value)
        channels = [float(item[:-1]) / 100 if item.endswith('%') else float(item) / 255 for item in parts[:3]]
        alpha = (float(parts[3][:-1]) / 100 if parts[3].endswith('%') else float(parts[3])) if len(parts) == 4 else 1
        return (*channels, alpha)
    raise ValueError('Unsupported color: ' + value)


def composite(front, back):
    alpha = front[3] + back[3] * (1 - front[3])
    if not alpha:
        return (0, 0, 0, 0)
    return tuple((front[i] * front[3] + back[i] * back[3] * (1-front[3])) / alpha for i in range(3)) + (alpha,)


def luminance(rgb):
    linear = [part / 12.92 if part <= 0.04045 else ((part + 0.055) / 1.055) ** 2.4 for part in rgb[:3]]
    return sum(part * weight for part, weight in zip(linear, (0.2126, 0.7152, 0.0722)))


def contrast(foreground, background, tokens):
    main = composite(color('--bg-main', tokens), (1, 1, 1, 1))
    background = composite(color(background, tokens), main)
    foreground = composite(color(foreground, tokens), background)
    light, dark = sorted((luminance(foreground), luminance(background)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


def pairs(tokens):
    backgrounds = ('--bg-main', '--bg-card', '--bg-secondary', '--bg-hover', '--bg-input', '--accent-soft')
    for foreground in ('--text-primary', '--text-secondary', '--text-muted'):
        for background in backgrounds:
            yield foreground, background
    for background in ('--bg-card', '--accent-soft'):
        yield '--color-primary', background
    for background in ('--color-primary', '--color-primary-hover'):
        yield '--on-primary', background
    for kind in ('success', 'warning', 'danger', 'info'):
        for background in ('--bg-card', '--bg-hover', '--accent-soft'):
            yield '--color-' + kind, background
        for background in ('--' + kind + '-soft', '--bg-' + kind, '--color-' + kind + '-soft'):
            if background in tokens:
                yield '--color-' + kind, background
    for foreground, background in (
        ('--sidebar-text', '--sidebar-bg'),
        ('--sidebar-muted', '--sidebar-bg'),
        ('--sidebar-active-text', '--sidebar-active'),
        ('--on-danger', '--color-danger'),
        ('--on-warning', '--color-warning'),
        ('--on-success', '--color-success'),
    ):
        if foreground in tokens and background in tokens:
            yield foreground, background

    for index in range(1, 9):
        yield '--gantt-text', '--gantt-color-' + str(index)
    for foreground in ('--sidebar-text', '--sidebar-muted', '--sidebar-accent'):
        yield foreground, '--sidebar-surface'
    for background in ('--bg-input', '--bg-card'):
        yield '--border-strong', background, 3.0
    yield '--on-info', '--color-info'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--css', type=Path, default=ROOT / 'static/css/themes.css')
    parser.add_argument('--all', action='store_true', help='Print every tested pair, including passing pairs')
    args = parser.parse_args()
    assert abs(contrast('#fff', '#000', {'--bg-main': '#fff'}) - 21) < 1e-9
    assert abs(contrast('#777', '#777', {'--bg-main': '#fff'}) - 1) < 1e-9
    failures = errors = 0
    for name, tokens in read_themes(args.css.read_text(encoding='utf-8-sig')).items():
        outcomes = []
        for pair in pairs(tokens):
            foreground, background = pair[:2]
            target = pair[2] if len(pair) == 3 else 4.5
            try:
                ratio = contrast(foreground, background, tokens)
                failed = ratio < target
                failures += failed
                outcomes.append(ratio)
                if failed or args.all:
                    print(f"{'FAIL' if failed else 'PASS'} [{name}] {foreground} / {background}: {ratio:.2f}:1")
            except ValueError as error:
                errors += 1
                print(f'ERROR [{name}] {foreground} / {background}: {error}')
        print(f'[{name}] {len(outcomes)} pairs, minimum across text and borders {min(outcomes):.2f}:1' if outcomes else f'[{name}] No valid color pairs')
    print(f'Token audit: {failures} below their target (text 4.5:1, borders 3:1); {errors} unresolved pairs. Does not evaluate font size or CSS cascade/opacity.')
    return 1 if failures or errors else 0


if __name__ == '__main__':
    sys.exit(main())
