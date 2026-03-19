%% plainnat.bst — BibTeX style for natbib (plain + natbib compatible)
%% This is a placeholder for the real plainnat.bst
%% In production, download from CTAN: https://ctan.org/pkg/natbib
ENTRY { author title journal year volume pages doi url note booktitle }
  {}
  { label }
STRINGS { s t }
FUNCTION {output} { write$ }
FUNCTION {article} { author " (" * year * "). " * title * ". " * journal * "." * output newline$ }
FUNCTION {inproceedings} { author " (" * year * "). " * title * ". In " * booktitle * "." * output newline$ }
FUNCTION {misc} { author " (" * year * "). " * title * "." * output newline$ }
READ
ITERATE {call.type$}
