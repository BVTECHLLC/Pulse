import re, sys

def convert(html):
    # Convert href="...X.html" and href="...X.html#frag" to extensionless.
    # Rules:
    #   foo.html        -> foo
    #   path/foo.html   -> path/foo
    #   index.html      -> ./  (same dir root)
    #   ../index.html   -> ../
    #   path/index.html -> path/
    #   ../             stays
    # Only touch internal links (not http/https/mailto). Preserve #fragments and ?query.
    def repl(m):
        pre = m.group(1)      # href="
        url = m.group(2)      # the URL
        post = m.group(3)     # "
        # split off fragment/query
        frag = ''
        for sep in ('#','?'):
            if sep in url:
                i = url.index(sep)
                frag = url[i:] + frag if False else url[i:]  # keep first sep onward
                url = url[:i]
                break
        if not url.endswith('.html'):
            return m.group(0)
        # strip .html
        base = url[:-5]
        # handle index
        if base == 'index':
            new = './'
        elif base.endswith('/index'):
            new = base[:-5]  # keep trailing slash: 'foo/index' -> 'foo/'
        else:
            new = base
        return f'{pre}{new}{frag}{post}'
    # match href=" ... " where url contains no scheme
    return re.sub(r'(href=")((?!https?:|mailto:|tel:|data:|//)[^"]*?\.html(?:[#?][^"]*)?)(")', repl, html)

if __name__ == '__main__':
    import glob, os
    files = sys.argv[1:]
    n=0
    for f in files:
        s=open(f,encoding='utf-8').read()
        c=convert(s)
        if c!=s:
            open(f,'w',encoding='utf-8').write(c); n+=1
    print(f"converted {n} files")
