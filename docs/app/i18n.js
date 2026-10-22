// Every sentence the page shows, in English, Italian and Spanish.

const S = {
  en: {
    title: "reflip in your browser",
    lede: "Check what a rewrite changed, estimate whether a model wrote a text, or rewrite one. All of it runs on this device.",
    promise: "Your text never leaves this device. The page counts four things and nothing else: the schema version, what was used, which page, which model. Never the text, its length, a hash, its language or a result.",
    see_sent: "What this page has sent",
    tab_facts: "Compare facts", tab_detect: "Detect", tab_rewrite: "Rewrite",
    text: "Text", text_ph: "Paste a text here.",
    after: "Rewritten text", after_ph: "Paste the rewritten version here.",
    compare: "Compare",
    facts_intro: "Numbers, names, negations and quantifiers: the words a paraphrase can change while still sounding right. No model, nothing to download.",
    facts_none: "No number, name, negation or quantifier changed.",
    facts_some: "{n} facts changed ({p} per 1,000 words).",
    numbers: "Numbers", names: "Names", negations: "Negations", quantifiers: "Quantifiers",
    gone: "gone", added: "new", neg_line: "{a} before, {b} after",
    facts_lang: "Facts are read in English, Italian and Spanish only, and this text looks like none of them.",
    facts_limit: "A check, not a proof: a claim reworded with every number and name intact is invisible to it.",
    q: { all: "all", some: "some", most: "most", many: "many", few: "few", only: "only", always: "always", sometimes: "sometimes", often: "often", usually: "usually", rarely: "rarely", at_least: "at least", at_most: "at most", more_than: "more than", less_than: "less than", about: "about" },
    detect_intro: "Two small models, Qwen2.5 0.5B base and instruct in 4-bit form, measure how predictable the text is. They are downloaded once ({size}) and kept in this browser. They run on the processor, about half a minute for a long text: on the graphics card the same files gave scores that the thresholds were not measured on.",
    detect_no_calib: "The detector's numbers are still being measured. Detection opens here once they are published.",
    download_detector: "Download the detector ({size})",
    check: "Check this text",
    tail: "Of {of} human texts of this length that were measured (Italian, Spanish and English), {k} scored at least this machine-like ({share}; 95% interval {lo} to {hi}).",
    verdict_machine: "Verdict: machine-like. The score is past a threshold that flagged at most {up} of human texts in {lang} at this length (95% upper bound).",
    verdict_none: "Verdict: no evidence of machine writing at this threshold. That is not proof a person wrote it.",
    refuse_short: "The text has {w} words. The shortest texts this was measured on had {min}, and below that the scores were not checked against anything.",
    refuse_lang: "The language could not be recognised as Italian, Spanish or English, the only three this was measured on.",
    refuse_one: "The text has fewer than two sentences, so this detector has nothing to read.",
    refuse_cell: "No verdict for {lang} at this length: AUROC {auc} (lower bound {lo}), {tpr} of machine texts caught, up to {up} of human texts flagged. The rule needs at least 0.85, half, and at most 2%.",
    refuse_cell_none: "No verdict for {lang} at this length: not enough measured texts.",
    learners: "Essays by people writing {lang} as a second language, at this length, crossed the threshold {k} times in {n} ({share}; up to {up}).",
    learners_none: "Not measured on people writing {lang} as a second language: no open corpus of their texts at this length was found.",
    vendor: "This cannot tell whether Claude or Gemini wrote a text from their watermarks: Anthropic's watermark (on Claude models launched since 2 August 2026) and Google's can only be read with secrets those companies keep.",
    lang_names: { en: "English", it: "Italian", es: "Spanish" },
    rewrite_intro: "A local model rewrites the text paragraph by paragraph. A paragraph whose facts changed is asked again once; the facts check below shows what is left.",
    rewrite_unmeasured: "These browser models have not been through reflip's benchmark. Read the facts check before using the result.",
    model: "Model", download_rewriter: "Download and rewrite ({size})", rewrite: "Rewrite",
    result: "Rewritten text", copy: "Copy", copied: "Copied",
    cancel: "Cancel", cancelled: "Cancelled.",
    downloading: "Downloading {done} of {total}", loading: "Loading into memory ({done} of {total})",
    working: "Working on this device. The network is locked until it ends.",
    rewriting: "Rewriting paragraph {i} of {n}",
    locked: "Network locked",
    no_gpu: "This browser cannot rewrite: it has no WebGPU with half-precision support. The facts check and detection still work. Recent Chrome, Edge or Safari on a computer usually can.",
    stored: "Models on this device: {list}.", forget: "Delete downloaded models", forgotten: "Deleted.",
    sent_none: "Nothing yet.", sent_gpc: "Your browser asks not to be tracked (Global Privacy Control or Do Not Track), so nothing is counted.",
    sent_intro: "Each line is one request to {host}, exactly as sent:",
    error: "Something went wrong: {m}",
    privacy: "Privacy", home: "About reflip", source: "Source",
  },
  it: {
    title: "reflip nel browser",
    lede: "Controlla cosa ha cambiato una riscrittura, stima se un testo l'ha scritto un modello, o riscrivilo. Tutto avviene su questo dispositivo.",
    promise: "Il tuo testo non lascia mai questo dispositivo. La pagina conta quattro cose e nient'altro: la versione dello schema, cosa è stato usato, quale pagina, quale modello. Mai il testo, la sua lunghezza, un hash, la lingua o un risultato.",
    see_sent: "Cosa ha inviato questa pagina",
    tab_facts: "Confronta i fatti", tab_detect: "Rileva", tab_rewrite: "Riscrivi",
    text: "Testo", text_ph: "Incolla qui un testo.",
    after: "Testo riscritto", after_ph: "Incolla qui la versione riscritta.",
    compare: "Confronta",
    facts_intro: "Numeri, nomi, negazioni e quantificatori: le parole che una parafrasi può cambiare continuando a suonare giusta. Nessun modello, niente da scaricare.",
    facts_none: "Nessun numero, nome, negazione o quantificatore è cambiato.",
    facts_some: "{n} fatti cambiati ({p} ogni 1.000 parole).",
    numbers: "Numeri", names: "Nomi", negations: "Negazioni", quantifiers: "Quantificatori",
    gone: "spariti", added: "nuovi", neg_line: "{a} prima, {b} dopo",
    facts_lang: "I fatti si leggono solo in inglese, italiano e spagnolo, e questo testo non sembra in nessuna delle tre.",
    facts_limit: "È un controllo, non una prova: un'affermazione riformulata lasciando intatti numeri e nomi gli sfugge.",
    q: { all: "tutti", some: "alcuni", most: "la maggior parte", many: "molti", few: "pochi", only: "solo", always: "sempre", sometimes: "a volte", often: "spesso", usually: "di solito", rarely: "raramente", at_least: "almeno", at_most: "al massimo", more_than: "più di", less_than: "meno di", about: "circa" },
    detect_intro: "Due modelli piccoli, Qwen2.5 0.5B base e instruct in forma a 4 bit, misurano quanto il testo è prevedibile. Si scaricano una volta ({size}) e restano in questo browser. Girano sul processore, circa mezzo minuto per un testo lungo: sulla scheda grafica gli stessi file davano punteggi diversi da quelli su cui sono state misurate le soglie.",
    detect_no_calib: "I numeri del rilevatore sono ancora in misura. Il rilevamento si apre qui appena sono pubblicati.",
    download_detector: "Scarica il rilevatore ({size})",
    check: "Controlla questo testo",
    tail: "Su {of} testi umani di questa lunghezza misurati (italiano, spagnolo e inglese), {k} sono risultati almeno così simili a una macchina ({share}; intervallo al 95% da {lo} a {hi}).",
    verdict_machine: "Verdetto: simile a una macchina. Il punteggio supera una soglia che ha segnalato al massimo il {up} dei testi umani in {lang} a questa lunghezza (limite superiore al 95%).",
    verdict_none: "Verdetto: nessun indizio di scrittura automatica a questa soglia. Non è la prova che l'abbia scritto una persona.",
    refuse_short: "Il testo ha {w} parole. I testi più corti su cui è stato misurato ne avevano {min}, e sotto quella soglia i punteggi non sono stati confrontati con niente.",
    refuse_lang: "La lingua non è stata riconosciuta come italiano, spagnolo o inglese, le sole tre su cui è stato misurato.",
    refuse_one: "Il testo ha meno di due frasi, quindi questo rilevatore non ha niente da leggere.",
    refuse_cell: "Nessun verdetto per i testi in {lang} a questa lunghezza: AUROC {auc} (limite inferiore {lo}), {tpr} dei testi automatici presi, fino al {up} dei testi umani segnalati. La regola chiede almeno 0,85, la metà, e al massimo il 2%.",
    refuse_cell_none: "Nessun verdetto per i testi in {lang} a questa lunghezza: troppo pochi testi misurati.",
    learners: "I temi di chi scrive in {lang} come seconda lingua, a questa lunghezza, hanno superato la soglia {k} volte su {n} ({share}; fino al {up}).",
    learners_none: "Non misurato su chi scrive in {lang} come seconda lingua: non si è trovato un corpus aperto di loro testi a questa lunghezza.",
    vendor: "Questo strumento non può dire se un testo l'ha scritto Claude o Gemini dalle loro filigrane: quella di Anthropic (sui modelli Claude usciti dal 2 agosto 2026) e quella di Google si leggono solo con segreti che le due aziende tengono per sé.",
    lang_names: { en: "inglese", it: "italiano", es: "spagnolo" },
    rewrite_intro: "Un modello locale riscrive il testo un paragrafo alla volta. Un paragrafo in cui un fatto è cambiato viene richiesto una seconda volta; il controllo qui sotto mostra cosa resta.",
    rewrite_unmeasured: "Questi modelli del browser non sono passati dal banco di prova di reflip. Leggi il controllo dei fatti prima di usare il risultato.",
    model: "Modello", download_rewriter: "Scarica e riscrivi ({size})", rewrite: "Riscrivi",
    result: "Testo riscritto", copy: "Copia", copied: "Copiato",
    cancel: "Annulla", cancelled: "Annullato.",
    downloading: "Scaricati {done} di {total}", loading: "Caricamento in memoria ({done} di {total})",
    working: "Al lavoro su questo dispositivo. La rete resta bloccata fino alla fine.",
    rewriting: "Riscrivo il paragrafo {i} di {n}",
    locked: "Rete bloccata",
    no_gpu: "Questo browser non può riscrivere: non ha WebGPU con la mezza precisione. Il controllo dei fatti e il rilevamento funzionano lo stesso. Di solito ci riescono Chrome, Edge o Safari recenti su un computer.",
    stored: "Modelli su questo dispositivo: {list}.", forget: "Cancella i modelli scaricati", forgotten: "Cancellati.",
    sent_none: "Ancora niente.", sent_gpc: "Il tuo browser chiede di non essere tracciato (Global Privacy Control o Do Not Track), quindi non si conta niente.",
    sent_intro: "Ogni riga è una richiesta a {host}, esattamente come è partita:",
    error: "Qualcosa è andato storto: {m}",
    privacy: "Privacy", home: "Cos'è reflip", source: "Codice",
  },
  es: {
    title: "reflip en el navegador",
    lede: "Comprueba qué cambió una reescritura, estima si un texto lo escribió un modelo, o reescríbelo. Todo ocurre en este dispositivo.",
    promise: "Tu texto nunca sale de este dispositivo. La página cuenta cuatro cosas y nada más: la versión del esquema, qué se usó, qué página, qué modelo. Nunca el texto, su longitud, un hash, su idioma ni un resultado.",
    see_sent: "Qué ha enviado esta página",
    tab_facts: "Comparar hechos", tab_detect: "Detectar", tab_rewrite: "Reescribir",
    text: "Texto", text_ph: "Pega aquí un texto.",
    after: "Texto reescrito", after_ph: "Pega aquí la versión reescrita.",
    compare: "Comparar",
    facts_intro: "Números, nombres, negaciones y cuantificadores: las palabras que una paráfrasis puede cambiar sin dejar de sonar bien. Sin modelo, nada que descargar.",
    facts_none: "No cambió ningún número, nombre, negación ni cuantificador.",
    facts_some: "{n} hechos cambiados ({p} por cada 1.000 palabras).",
    numbers: "Números", names: "Nombres", negations: "Negaciones", quantifiers: "Cuantificadores",
    gone: "desaparecidos", added: "nuevos", neg_line: "{a} antes, {b} después",
    facts_lang: "Los hechos solo se leen en inglés, italiano y español, y este texto no parece ninguno de los tres.",
    facts_limit: "Es una comprobación, no una prueba: una afirmación reformulada con todos los números y nombres intactos se le escapa.",
    q: { all: "todos", some: "algunos", most: "la mayoría", many: "muchos", few: "pocos", only: "solo", always: "siempre", sometimes: "a veces", often: "a menudo", usually: "normalmente", rarely: "raramente", at_least: "al menos", at_most: "como máximo", more_than: "más de", less_than: "menos de", about: "aproximadamente" },
    detect_intro: "Dos modelos pequeños, Qwen2.5 0.5B base e instruct en forma de 4 bits, miden lo predecible que es el texto. Se descargan una vez ({size}) y se quedan en este navegador. Funcionan en el procesador, cerca de medio minuto para un texto largo: en la tarjeta gráfica los mismos archivos daban puntuaciones distintas de aquellas con las que se midieron los umbrales.",
    detect_no_calib: "Los números del detector todavía se están midiendo. La detección se abre aquí en cuanto se publiquen.",
    download_detector: "Descargar el detector ({size})",
    check: "Comprobar este texto",
    tail: "De {of} textos humanos de esta longitud que se midieron (italiano, español e inglés), {k} puntuaron al menos así de parecidos a una máquina ({share}; intervalo del 95% de {lo} a {hi}).",
    verdict_machine: "Veredicto: parecido a una máquina. La puntuación supera un umbral que marcó como mucho el {up} de los textos humanos en {lang} a esta longitud (límite superior del 95%).",
    verdict_none: "Veredicto: ningún indicio de escritura automática en este umbral. No es una prueba de que lo escribiera una persona.",
    refuse_short: "El texto tiene {w} palabras. Los textos más cortos con los que se midió tenían {min}, y por debajo las puntuaciones no se compararon con nada.",
    refuse_lang: "El idioma no se reconoció como italiano, español o inglés, los únicos tres con los que se midió.",
    refuse_one: "El texto tiene menos de dos frases, así que este detector no tiene nada que leer.",
    refuse_cell: "Sin veredicto para el {lang} a esta longitud: AUROC {auc} (límite inferior {lo}), {tpr} de los textos automáticos detectados, hasta el {up} de los textos humanos marcados. La regla pide al menos 0,85, la mitad y como mucho el 2%.",
    refuse_cell_none: "Sin veredicto para el {lang} a esta longitud: pocos textos medidos.",
    learners: "Las redacciones de quienes escriben en {lang} como segunda lengua, a esta longitud, superaron el umbral {k} veces de {n} ({share}; hasta el {up}).",
    learners_none: "No medido con quienes escriben en {lang} como segunda lengua: no se encontró un corpus abierto de sus textos a esta longitud.",
    vendor: "Esto no puede decir si un texto lo escribió Claude o Gemini a partir de sus marcas de agua: la de Anthropic (en los modelos Claude lanzados desde el 2 de agosto de 2026) y la de Google solo se leen con secretos que esas empresas guardan.",
    lang_names: { en: "inglés", it: "italiano", es: "español" },
    rewrite_intro: "Un modelo local reescribe el texto párrafo a párrafo. Un párrafo en el que cambió un hecho se pide otra vez; la comprobación de abajo muestra lo que queda.",
    rewrite_unmeasured: "Estos modelos del navegador no han pasado por el banco de pruebas de reflip. Lee la comprobación de hechos antes de usar el resultado.",
    model: "Modelo", download_rewriter: "Descargar y reescribir ({size})", rewrite: "Reescribir",
    result: "Texto reescrito", copy: "Copiar", copied: "Copiado",
    cancel: "Cancelar", cancelled: "Cancelado.",
    downloading: "Descargados {done} de {total}", loading: "Cargando en memoria ({done} de {total})",
    working: "Trabajando en este dispositivo. La red queda bloqueada hasta el final.",
    rewriting: "Reescribiendo el párrafo {i} de {n}",
    locked: "Red bloqueada",
    no_gpu: "Este navegador no puede reescribir: no tiene WebGPU con media precisión. La comprobación de hechos y la detección funcionan igual. Suelen poder Chrome, Edge o Safari recientes en un ordenador.",
    stored: "Modelos en este dispositivo: {list}.", forget: "Borrar los modelos descargados", forgotten: "Borrados.",
    sent_none: "Nada todavía.", sent_gpc: "Tu navegador pide no ser rastreado (Global Privacy Control o Do Not Track), así que no se cuenta nada.",
    sent_intro: "Cada línea es una petición a {host}, tal como salió:",
    error: "Algo salió mal: {m}",
    privacy: "Privacidad", home: "Qué es reflip", source: "Código",
  },
};

export const LANGS = ["en", "it", "es"];

export function pickLanguage() {
  try {
    const saved = localStorage.getItem("reflip.ui");
    if (LANGS.includes(saved)) return saved;
  } catch {}
  const nav = (navigator.language || "en").slice(0, 2);
  return LANGS.includes(nav) ? nav : "en";
}

export function strings(lang) {
  return S[lang] || S.en;
}

export function fill(template, vars = {}) {
  return template.replace(/\{(\w+)\}/g, (_, k) => (k in vars ? String(vars[k]) : `{${k}}`));
}

export function pct(x, lang) {
  return new Intl.NumberFormat(lang, { style: "percent", maximumFractionDigits: 1 }).format(x);
}

export function num(x, lang, digits = 2) {
  return new Intl.NumberFormat(lang, { maximumFractionDigits: digits }).format(x);
}

export function bytes(n, lang) {
  const gb = n / 1e9;
  return gb >= 1 ? `${num(gb, lang, 2)} GB` : `${num(n / 1e6, lang, 0)} MB`;
}
