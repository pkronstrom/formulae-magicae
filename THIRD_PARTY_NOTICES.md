# Third-party notices

Formulae Magicae is MIT-licensed. The following bundled resources retain their
own licenses and attribution.

## Summon wordlists

`skills/summon/wordlist.en.txt` is derived from the Electronic Frontier
Foundation's Short Wordlist, licensed under CC BY 3.0 US. The Finnish wordlist is
hand-curated by the Formulae Magicae author. Portal may carry local copies of the
same wordlists so that its individually installed plugin remains self-contained.

## Bento Slides fonts

The font data under `skills/bento-slides/styles/fonts/` is distributed according
to the license texts stored in that same directory:

- Fraunces, Instrument Sans, and Space Mono: SIL Open Font License 1.1.
- Latin Modern: GUST Font License.

The bundled Bento runtime is MIT-licensed and carries its license and dependency
attribution in the opening comment of
`skills/bento-slides/runtime/Bento_Slides.bento.html`. Its embedded libraries
include reveal.js and Moveable, both under the MIT License.

## Visualize fonts

The Latin Modern font data embedded by `skills/visualize/` is distributed under
the GUST Font License. A copy is included at
`skills/visualize/LICENSE-GUST-LatinModern.txt`.

The Visualize HTML template also incorporates LaTeX.css styles under the MIT
License; the upstream license reference is retained in the template source.

## Runtime projects

Some skills drive independently installed open-source tools, including croc,
ntfy, yt-dlp, ffmpeg, Kokoro, and OpenSpec. Those tools are not bundled here and
remain under their respective licenses.
