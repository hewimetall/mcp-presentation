# syntax=docker/dockerfile:1
# PDF builder — TeX Live (XeLaTeX / latexmk) + fonts / Cyrillic / Beamer deps.
# Mount workspace at /work. Entry: latexmk → out/main.pdf

FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    TEXMFHOME=/tmp/texmf-home \
    TEXMFVAR=/tmp/texmf-var \
    TEXMFCONFIG=/tmp/texmf-config

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    fontconfig \
    fonts-dejavu \
    fonts-liberation \
    fonts-noto-core \
    fonts-noto-cjk \
    ghostscript \
    latexmk \
    make \
    perl \
    python3 \
    texlive-base \
    texlive-bibtex-extra \
    texlive-extra-utils \
    texlive-fonts-extra \
    texlive-fonts-recommended \
    texlive-font-utils \
    texlive-lang-cyrillic \
    texlive-lang-european \
    texlive-latex-base \
    texlive-latex-extra \
    texlive-latex-recommended \
    texlive-luatex \
    texlive-pictures \
    texlive-plain-generic \
    texlive-science \
    texlive-xetex \
    && fc-cache -f \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /work

COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["pdf"]
