# Consiglio sull'espansione di reflip

21 ottobre 2026. Cinque consiglieri indipendenti, cinque revisioni anonime tra pari, un presidente.
Tutti Claude Opus 5.5 a sforzo massimo, metodo del Consiglio di LLM (Karpathy).
Il testo di ogni voce è riportato integralmente, così come è stato restituito.

## La domanda posta al consiglio

DOMANDA AL CONSIGLIO: in che modo reflip può espandersi in generale, su quattro fronti: rilevamento, misura, privacy, prodotto? Che cosa dovrebbe diventare, che cosa non dovrebbe fare, e da dove partire?

CHE COS'È REFLIP OGGI (repo pubblico github.com/nerln/reflip, sito nerln.github.io/reflip/, licenza MIT, autore: un dottorando a Valencia che lavora da solo su un MacBook da 16 GB, con l'aiuto di agenti):
- Nasce per togliere dal testo il watermark statistico che Anthropic applica a ogni modello Claude lanciato dal 2 agosto 2026 ("una versione di SynthID-Text", annuncio Anthropic; obbligo dall'art. 50 dell'AI Act). Il watermark sta nella scelta delle parole: a ogni passo un segreto più i 4 token precedenti decidono una moneta per ogni candidato. Cambiare un token ne ri-randomizza cinque. Misurato: una modifica ogni 5 token porta il rilevatore a rumore; ogni 6 ne lascia passare il 17%; ogni 10 il 50%; il punteggio scende esattamente in proporzione alle posizioni rimaste intatte.
- Il valore dichiarato è la misura, non la riscrittura: sull'implementazione pubblica di SynthID-Text con una chiave propria, su 24 testi marcati (z medio 17,6): togliere i caratteri invisibili (quello che fanno oltre quaranta siti "watermark remover") non sposta nulla; regole senza modello portano a 15,8; parafrasi con un modello locale da 4B (qwen3, Ollama) porta a 0,6 (23/24 sotto soglia); parafrasi con controllo di copertura a 0,28 (24/24), similarità di significato 0,955, 74% delle parole cambiate, circa 5.800 token per 1.000 parole, 17 s a testo.
- Ha una CLI con contratto JSON per agenti, un'app macOS in SwiftUI (finestra in colonna, finestra dei modelli con ricerca su Hugging Face e un bottone che misura un modello sul posto), trasformazioni aggiuntive caricabili da una cartella dell'utente. È nella "flotta" del sito porto dell'autore.
- Limiti misurati sul campo: su prosa tecnica densa (un sommario di 575 parole con circa 50 numeri) parafrasi e infill la distruggono, con 21 e 32 rotture di significato contate (autori inventati, "four" diventato "five", un modello inesistente fuso da due nomi veri); il modello da 8B fa più danni del 4B, perché sbaglia in modo fluente. Su messaggi brevi di chat in italiano e spagnolo non serve: sotto circa 150 token non c'è watermark misurabile, e la parafrasi cancella l'idioletto. L'italiano viene peggio dell'inglese. Il controllo sulle sole cifre non basta.
- Il watermark di Anthropic e quelli di Google NON si possono rilevare né verificare senza le loro chiavi segrete: tutto ciò che reflip misura è sull'algoritmo pubblico con una chiave propria.

CHE COSA SI STA COSTRUENDO ADESSO (richiesta dell'autore, già in corso):
1. La direzione inversa, il rilevamento: (a) il rilevatore del watermark, solo per testi marcati con una chiave nota; (b) rilevatori zero-shot aperti, Binoculars e Fast-DetectGPT su coppie di modelli Qwen2.5 base/instruct da 0,5B e 1,5B (le sole che girano su questo Mac e che esistono anche in ONNX per il browser), più perplessità e burstiness alla GPTZero come base. Protocollo pre-registrato: 150 testi umani e 40 di macchina per lingua (it, es, en) e per lunghezza (sotto 100 parole, 100-300, oltre 300), umani da Wikipedia e da notizie (BBC, El País, Il Post), macchina da tre famiglie (Qwen3 4B, Gemma 3 4B, Claude Haiku 5.5), più testi riscritti da reflip. AUROC e TPR all'1% di falsi positivi, metà dei dati per calibrare e metà per misurare. L'output all'utente è calibrato, con incertezza, e rifiuta un verdetto sotto la lunghezza minima che i numeri giustificano. I numeri completi sono in produzione: una prova su due paragrafi dà Binoculars 1,00 per il testo umano e 0,91 per quello di macchina, circa 0,7 s a testo.
2. Una versione web interamente lato client: dal sito l'utente scarica nel browser un modello supportato (WebGPU, transformers.js o ONNX) e fa riscrittura e rilevamento solo sul suo dispositivo. Il sito raccoglie statistiche d'uso aggregate senza cookie (pagina vista, funzione usata, modello scelto, esito, capacità del dispositivo) ma MAI il testo incollato, né la sua lunghezza, né hash o grandezze derivate, imposto nel codice: CSP connect-src limitata, nessuna richiesta di rete durante l'elaborazione, un test che fallisce se un payload di statistiche contiene testo dell'utente. Privacy policy aggiornata. L'autore vive in Spagna (GDPR, AEPD).
3. L'autore vuole che reflip "diventi un tool molto usato".

CONTESTO CHE PESA: lo strumento è a doppio uso per costruzione (toglie e rileva). Il Code of Practice europeo sulla trasparenza impegna i firmatari (tra cui Anthropic, Google, OpenAI) a non promuovere strumenti per aggirare le marcature e chiede ai deployer di non toglierle; non vincola un terzo che pubblica codice. Gli strumenti concorrenti (oltre 40 tra repo e siti) promettono rimozioni che nessuno può verificare; nessuno pubblica numeri prima/dopo con il costo in qualità. L'autore tiene molto alla misura onesta: nessun numero senza misura, ogni limite scritto.

## I cinque consiglieri

### Il Bastian Contrario

Il difetto fatale non è tecnico: "molto usato" e "misura onesta" tirano in direzioni opposte, e i tuoi numeri dicono già chi userà reflip. Sotto i 150 token non serve, sulla prosa tecnica rompe il significato, in italiano rende peggio. Resta un solo terreno: prosa generica lunga, in inglese. Compiti, tesine, articoli SEO. Se cresce, cresce lì, col nome di un dottorando sopra.

**Rilevamento.** Mettere "riscrivi" e "sembra umano?" nella stessa pagina regala un oracolo locale e illimitato: si riscrive finché Binoculars dice umano. È l'attacco adattivo da manuale: la metà che difende serve quella che attacca. Nel protocollo, poi, ci sono tre buchi.

Primo: per PREREG gli umani fissano i falsi positivi, cioè il numero che conta per chi viene accusato. Ma l'accusato non è nel corpus. Wikipedia e giornali sono prosa curata e rivista. L'accusato è uno studente che scrive in inglese come seconda lingua, o un testo passato da DeepL Write: sono i casi su cui i rilevatori a perplessità sbagliano di più (Liang et al. 2023, sui saggi TOEFL).

Secondo: la soglia all'1% nasce da 225 umani di tre lingue insieme, ma si verifica cella per cella su 75. Zero falsi positivi su 75 è compatibile con un tasso vero fino a circa il 5%. E la regola di rifiuto non guarda il tasso di falsi positivi della cella. Guarda l'AUROC e un "almeno metà" contato su 20 testi di macchina (10 su 20 vuol dire tra 27% e 73%). L'italiano può così prendere un verdetto "all'1%" che i suoi dati non reggono.

Terzo: "gli stessi pesi" nel browser valgono solo a precisione piena. In q4 o q8, su WebGPU o in WASM, una soglia di coda calibrata sul Mac non è garantita. Ogni coppia file-backend va calibrata a parte.

**Misura.** La colonna "meaning kept" è il coseno di multilingual-e5-small, 0,955. È una metrica cieca proprio agli errori che hai contato sul campo, perché "four" che diventa "five" sposta appena un embedding. Il tuo vantaggio sui quaranta siti è misurare il costo, e il costo lo misuri con lo strumento sbagliato. Serve un conteggio di fatti rotti (numeri, nomi, autori) ogni 1.000 parole, per lingua. E ogni modello offerto nel browser, più piccolo del 4B misurato, vuole la sua riga nella tabella.

**Privacy.** "Esito" è una grandezza derivata dal testo. Un rifiuto per lunghezza rivela la lunghezza, e una durata, se c'è, rivela i token. Il test che cerca testo nel payload non vede né l'una né l'altra: serve uno schema chiuso, a valori enumerati, senza durate né punteggi. Poi c'è il dispositivo: spedire alle statistiche le sue capacità ricade nell'art. 5(3) ePrivacy e nel 22.2 della LSSI anche senza cookie (linee guida EDPB 2/2023). Leggerle per scegliere il modello è necessario; spedirle no.

**Prodotto.** La domanda che eviti: costruisci tutto con Claude Code e generi i testi di macchina con Haiku. Hai letto che cosa dicono i termini di Anthropic su chi aggira le sue marcature? Se la risposta è ambigua, il rischio non è una causa: è perdere lo strumento con cui lavori.

Da dove partire: niente web prima di tre cose. Un set umano scritto in seconda lingua e passato dai correttori, il conteggio dei fatti rotti, la calibrazione sul file ONNX vero. E cambia la metrica da "molto usato" a "molto citato": giornalisti, ricercatori e regolatori citano chi ha i numeri, gli studenti usano chi promette.

### Il Pensatore dai Primi Principi

La domanda presuppone un prodotto in cerca di funzioni. Ma reflip ha una sola cosa che i quaranta concorrenti non hanno: uno strumento che dice quanto costa una trasformazione e che cosa ottiene, appoggiato a una legge scritta su carta. Deve diventare il banco su cui si misura chiunque trasformi o giudichi testo, con un rimuovitore di riferimento che dichiara il proprio costo.

**Misura.** La tabella dà alla parafrasi "meaning kept 0,955", ma sul sommario da 575 parole ha fatto 21 rotture. Il README ammette già che quel punteggio non vede gli errori di grammatica. Non vede nemmeno "four" diventato "five", perché un coseno misura l'argomento, non i fatti. La colonna giusta è un'altra: fatti alterati per 1.000 parole (cifre, numeri in lettere, nomi propri, negazioni, quantificatori), contati per differenza meccanica.

La causa delle rotture sta nel codice, non nel watermark: `choose_slots` sceglie "content word first" ([words.py:57](/Users/eugenionerelli/dev/reflip/reflip/words.py:57)). La legge chiede una modifica ogni cinque token, non dice quale. La moneta di un fatto si ri-lancia cambiando uno dei quattro token prima, quindi proteggere "four" non costa copertura. Restano intatte solo le finestre fatte tutte di fatti. La loro quota dà lo z residuo prima di toccare una parola: se sono il 10%, un testo da 17,6 scende a circa 1,8.

**Rilevamento.** Chi chiede di togliere il watermark di solito vuole che il testo non sembri scritto da una macchina. reflip toglie la prova (le monete legate alla chiave), ma l'impronta (la perplessità bassa) può restare. Se Binoculars segna come macchina l'output di reflip, va scritto in prima pagina. Da non fare mai: tarare la riscrittura sui propri rilevatori. I due righelli diventerebbero uno, e reflip diventerebbe l'umanizzatore che dovrebbe giudicare.

Il tasso di falsi positivi appartiene alla popolazione, non al rilevatore. L'1% del PREREG si misura su Wikipedia, BBC, El País e Il Post: prosa nativa, curata, in parte già letta dai modelli. Gli accusati invece saranno studenti e non madrelingua (Liang et al., 2023: oltre metà dei temi TOEFL presi per macchina). Le strade sono due: si aggiunge un corpus di apprendenti (il CAES del Cervantes), oppure il verdetto nomina la popolazione: "1% di falsi positivi su testi di giornale".

**Privacy.** "Esito" è una grandezza derivata dal testo. Un verdetto è un bit calcolato sul testo incollato, e "rifiutato perché troppo corto" rivela la lunghezza, cioè proprio ciò che la regola vieta. Va tolto. La promessa poi va resa verificabile: scaricato il modello, la pagina deve funzionare a rete staccata. Dieci secondi col Wi-Fi spento convincono più di una CSP.

**Prodotto.** Per uno strumento di misura, "molto usato" vuol dire citato. Il fatto più citabile c'è già: togliere i caratteri invisibili, cioè quello che fanno quasi tutti i siti, non sposta lo z di un centesimo. Il passo dopo è una classifica pubblica dei rimuovitori esistenti, misurati sul vostro banco, con z e fatti rotti. Il rilevatore a chiave nota è il righello, non una funzione per gli utenti: nessun utente ha una chiave.

**Da dove partire.** Prima del browser, un giorno di lavoro. Il parametro `eligible` esiste già, nato per URL e code span. Estendetelo ai fatti e fate scegliere prima parole funzionali e punteggiatura. Poi aggiungete la colonna dei fatti e rilanciate sui 24 testi e sul sommario denso. Se le rotture scendono verso zero a parità di copertura, il limite sul testo tecnico cade e sapete quale modello serve al browser. Altrimenti avete misurato il prezzo vero.

### L'Espansionista

**Il valore nascosto è il metro, non la gomma.** Oltre quaranta strumenti promettono di togliere il watermark, e nessuno pubblica il prima e il dopo. reflip ha già il banco: corpus, bench, frazione di posizioni intatte, costo in significato. Deve diventare il laboratorio aperto che misura da dove viene un testo, con tre uscite su un solo motore: audit per chi marca, verdetto per chi giudica, diff per chi riscrive.

**Misura: il cliente che nessuno guarda è chi il watermark lo deve mettere.** L'art. 50 obbliga ogni fornitore di un sistema che genera testo, non solo Anthropic e Google. Vale anche per la startup che serve Gemma 3 dietro il suo chatbot. Per marcare un modello aperto, la via più corta è SynthID-Text dentro transformers con una chiave propria, lo stesso algoritmo su cui reflip misura. E la norma chiede soluzioni robuste e affidabili per quanto tecnicamente possibile: qualcuno deve dire quanto. `reflip audit --key mia.json --model gemma3:4b` produce l'allegato:
- la tabella del README rifatta sul modello e sulla chiave del fornitore;
- la curva «una modifica ogni k token»;
- la lunghezza sotto cui il rilevatore non vede.

È il penetration test del watermark: il doppio uso diventa la credenziale.

**Rilevamento: non «sì o no», ma quanto e dove.** Con la chiave in mano, la legge di proporzionalità si può usare al contrario. Si stima la quota di posizioni intatte e si colorano le frasi che conservano la marca, fino a dire «il 60% delle posizioni porta ancora la nostra marca». Nello zero-shot ciò che vale è la tabella pre-registrata per lingua e lunghezza, con il rifiuto. Una frase come «sotto N parole, in italiano, nessuno dei rilevatori misurati dà un verdetto all'1% di falsi positivi» può entrare nelle linee guida degli atenei. Pubblicate il benchmark su Hugging Face, con le notizie come elenco di URL più lo script, e invitate GPTZero e gli altri a misurarsi lì sopra. Così reflip diventa l'arbitro, non il quarantunesimo concorrente.

**Il pezzo più grande: il diff dei fatti.** Le 21 e 32 rotture di significato contate a mano («four» diventato «five», gli autori inventati) sono il problema di chiunque faccia ripulire a un modello un paper, una traduzione, un contratto. `reflip diff originale.md riscritto.md` elencherebbe i numeri cambiati (anche quelli scritti in lettere), i nomi, le citazioni e le negazioni. Non ha doppio uso, ha un pubblico molto più largo di quello del watermark, ed è il freno che rende pubblicabile la riscrittura di reflip stesso. Con il contratto JSON che esiste già, diventa il controllo che ogni agente di scrittura chiama prima di consegnare.

**Privacy come argomento di vendita.** Una scuola che carica i temi degli studenti su un servizio americano deve avere un contratto di trattamento e una base legale per il trasferimento. Nel browser, senza rete, il problema non nasce. Rendetelo verificabile: una pagina «guarda tu» che mostra il registro di rete vuoto durante l'elaborazione.

**Che cosa non fare:** la vetrina da remover. È il mercato più affollato e non ha difese, perché qualunque modello da 4B sa parafrasare. La riscrittura resta dentro reflip come attacco di riferimento, non come insegna.

**Da dove partire:** `reflip audit` su Gemma 3 4B con chiave propria. Corpus, bench e frazione intatta esistono già, e il rilevatore a chiave nota è in costruzione. Al lancio, due pagine: il rapporto di robustezza e la misura dei quaranta remover sulla stessa tabella. La seconda porta i giornalisti, la prima porta chi resta, e il diff porta la folla.

### L'Estraneo

**Il lettore deve ricavare da solo la conseguenza, e non ci arriva.** Il README scrive «nobody outside Anthropic holds the secret» e poco dopo «with a secret of its own, on an open model». Per te, lette insieme, vogliono dire: non posso dirti se il tuo testo di Claude è ancora marcato. Io leggo la prima riga, «no longer registers on the detector», poi «24 of 24», e concludo che funziona su Claude. Quella frase va in cima, detta come la direbbe chi incolla il testo: «Nessuno fuori da Anthropic può dirti se il tuo testo è ancora marcato, nemmeno noi. Ecco cosa possiamo dirti.» Nessun concorrente la scrive.

**Il numero che capisco è quello sbagliato.** L'unica colonna che si legge senza aiuto è «meaning kept (cosine) 0.955», e io la leggo «conserva il 95% del significato». Sul campo, intanto, «four» è diventato «five» e sono spuntati autori inventati. Al posto di quella colonna metterei quante cifre, nomi e negazioni sono cambiati. Nell'app, l'originale accanto alla riscrittura, da controllare a occhio.

**Il rilevatore parla al contrario.** «Binoculars 1,00 per l'umano, 0,91 per la macchina»: da fuori, 1,00 sembra «certamente IA». Che il punteggio più basso indichi la macchina, e se 0,09 di differenza sia tanto o niente, lo sa solo chi ha letto il paper. Poi c'è la probabilità «sotto un prior del 50%». Un insegnante legge «91%» e si ferma lì, anche se nella sua classe un modello scrive un compito su dieci e quel punteggio vale molto meno. La frase giusta è già nel PREREG: «3 testi umani su 100 hanno avuto un punteggio così». Lascerei solo quella.

**Due unità di misura e un vocabolario privato.** Il limite del watermark è in token (sotto 150 non si misura), il rilevatore invece conta in parole. Nessun utente sa quanto è lungo un token, e in italiano ancora meno. Poi stride, infill, coverage-checked, positions intact, e il nome stesso: «reflip» si capisce solo dopo aver letto la teoria delle monete. Userei una sola unità: le parole.

**La privacy ha due crepe visibili.** Nello stesso punto elenco ci sono «Nothing leaves your machine» e «Any OpenAI-compatible endpoint works too». Per la versione web prometti «mai grandezze derivate dal testo», ma tra le statistiche c'è l'«esito». Se è il verdetto, deriva dal testo. Se vuol dire «riuscito/errore», va scritto così. E «capacità del dispositivo» raccolte senza cookie, da fuori, suonano come fingerprinting. Il rimedio: accanto al bottone, il payload esatto che parte, in chiaro.

**Per chi è?** Il README non lo dice, perché tu lo sai. I limiti misurati però disegnano l'utente da soli: inglese, più di un paragrafo, pochi numeri, nessuna voce personale da salvare. Da fuori, è una tesina. Se l'utente non lo nomini tu, lo nomineranno gli altri. Manca anche la frase che l'utente direbbe ad alta voce: «lo tolgo perché...».

**Togliere e rilevare sullo stesso sito**, per chi non ti conosce, è un negozio di grimaldelli che vende anche serrature. Le due cose stanno insieme solo nella cornice che già dichiari, detta in parole comuni: quanto ogni riscrittura nasconde ai rilevatori aperti e quanto rompe del testo. Il prodotto è quel prezzo, mostrato su ogni testo.

**Da dove partire.** Dai la prima schermata a qualcuno che non ha mai sentito «SynthID» e fagli tre domande. Il mio testo di Claude è ancora marcato? Il significato è cambiato? Per chi è questo strumento? Se sbaglia anche una sola risposta, riscrivi la schermata prima di costruire altro.

Fonti lette: [README.md](/Users/eugenionerelli/dev/reflip/README.md), [PREREG.md](/Users/eugenionerelli/dev/reflip/docs/detect/PREREG.md)

### L'Esecutore

**Rilevamento: chiudere, non allargare.** Ho contato i file in `/Users/eugenionerelli/dev/reflip/data/detect/`. I testi umani ci sono tutti, 1.350 su 1.350. Quelli di macchina sono 231 su 360 nel momento in cui li ho contati: Haiku ha finito, Qwen3 è poco oltre metà, Gemma 3 non è partito. Le riscritture sono zero su 45. A 0,7 s a testo, misurare 1.755 testi costa una ventina di minuti, quindi il collo di bottiglia è la generazione.

C'è però un buco da chiudere subito. In italiano Haiku ha consegnato sotto le 301 parole 8 dei 16 testi lunghi chiesti. Quegli 8 sono finiti nel medio, che è già pieno. Così la cella lunga-italiano arriva a 40 solo se Qwen3 e Gemma non ne sbagliano nemmeno una delle loro 32 richieste.

Lunedì si aggiungono richieste lunghe in italiano, su argomenti nuovi, e si annotano con la data in [PREREG.md](/Users/eugenionerelli/dev/reflip/docs/detect/PREREG.md): sono pulite perché fatte prima di vedere un numero. Poi Gemma, le riscritture e il punteggio. La tabella per cella va nel README nello stesso formato di quella della rimozione, e le celle senza verdetto ci vanno scritte come tali. Nessun quarto rilevatore e nessuna quarta lingua prima di quella tabella.

**Misura: le rotture diventano un test.** Il sommario da 575 parole con le sue 21 e 32 rotture è il caso più utile che reflip abbia, e va trasformato in fixture. I tuoi esempi sono di due tipi: aggiunte (autori inventati, il modello fuso da due nomi) e sostituzioni ("four" diventato "five"). Una guardia deterministica li prende entrambi. Ogni nome proprio e ogni numero, in cifre o in lettere nelle tre lingue, deve comparire sia prima sia dopo. Se manca, il paragrafo si richiede, e al secondo fallimento si rifiuta. Il criterio per dire che funziona: la guardia segnala ogni rottura della fixture che tocca un nome o un numero, e il numero di quelle che le sfuggono va scritto nel README. Lo stesso giorno va fatto il rifiuto sotto i 150 token: il contratto ha già `{"ok": false, "reason": ...}`, basta una riga.

**Privacy: due tagli.** Il campo "esito" contraddice la tua stessa regola. Un rifiuto per lunghezza dice che il testo stava sotto una soglia, e un verdetto dice com'era il testo. Toglilo dalla v1: meno campi vuol dire meno da difendere davanti all'AEPD. La v1 web fa solo rilevamento con la coppia da 0,5B, mentre il riscrittore da 2,5 GB resta nella CLI e nell'app.

Ci sono due trappole pratiche:
- GitHub Pages non riceve POST, quindi il contatore deve stare altrove, per esempio un Worker Cloudflare come cambusa-sync.
- I pesi arrivano da Hugging Face, che rimanda i file grossi su altri host, e una connect-src stretta blocca anche quelli. Va provata su un download vero prima del lancio.

Il test sul payload si scrive in un browser headless. Si incolla una stringa riconoscibile, si eseguono le due funzioni e si verifica due cose: nessuna richiesta contiene la stringa, e durante l'elaborazione non parte nessuna richiesta.

**Prodotto: il lancio è un benchmark.** Le trasformazioni si caricano da una cartella, quindi ogni "remover" open source dei quaranta si collega con un adattatore di poche righe. Prendi i dieci con più stelle, collegali e lancia `reflip bench`. "Abbiamo misurato i dieci rimuovi-watermark più popolari", con la tabella sotto, è un post che nessun concorrente può scrivere. Oggi reflip si installa solo da un clone del repo: un pacchetto su PyPI vale più di qualunque funzione nuova.

**Da non fare:** niente che non abbia un primo passo. "Rileva il watermark di Claude" non ce l'ha, e non deve comparire nemmeno come "in arrivo". E niente modello da 8B per salvare l'italiano: è già misurato che fa peggio.

## Le revisioni anonime

Per la revisione le risposte sono state anonimizzate così: A = L'Espansionista; B = L'Esecutore; C = Il Bastian Contrario; D = L'Estraneo; E = Il Pensatore dai Primi Principi.

### Revisione 1

**1. La più forte: E.** Trova nel codice la causa del limite più grave e ne fa un esperimento da un giorno, con la previsione scritta prima. Ho controllato: `choose_slots` sceglie davvero «content word first» ([words.py:57](/Users/eugenionerelli/dev/reflip/reflip/words.py:57)), e `eligible` esiste già. E vede anche che il falso positivo dipende dalla popolazione (rimedio: il CAES), toglie «esito» e vieta di tarare la riscrittura sui propri rilevatori. Le sfugge però che `_plan_slots` serve solo `infill` e `hybrid` ([llm.py:652](/Users/eugenionerelli/dev/reflip/reflip/transforms/llm.py:652)). La `paraphrase` riscrive blocchi interi, quindi le sue 21 rotture restano. Per quelle serve la guardia di B.

**2. Il punto cieco più grande: B.** Conta i file, ma non chiede se sono quelli giusti. Chiude una tabella il cui numero decisivo, il falso positivo, viene da prosa nativa e curata, non da chi verrà accusato (C, E). Poi lancia come v1 web proprio il rilevatore da 0,5B, calibrato sul Mac e non sul file ONNX quantizzato (C). È il piano più facile da eseguire, e porta al pubblico la funzione più dannosa nella forma meno verificata.

**3. Che cosa hanno mancato tutte e cinque.**
- **Una misura su un watermark vero.** Tutte accettano che il watermark vero non si possa misurare. Ma Google ha dal 2025 il portale SynthID Detector, con una lista d'attesa per ricercatori, e il servizio Gemini marca il testo. Testi Gemini controllati prima e dopo reflip darebbero l'unica riga misurata su un watermark in produzione. Se le condizioni d'uso lo vietano, va scritto anche questo.
- **La letteratura.** A ed E vogliono fare di reflip l'arbitro. Ma RAID (Dugan et al., ACL 2024) classifica già i rilevatori sotto attacco, GPTZero compreso, e MarkMyWords (Piet et al., 2023) misura robustezza e qualità dei watermark. Né il README né docs/ li citano. La nicchia va definita rispetto a loro: italiano e spagnolo, testi corti, i remover consumer, le rotture di fatti.

### Revisione 2

**1. La più forte è E.** Trasforma il limite più grave, i fatti rotti, in un'ipotesi meccanica che si prova in un giorno. La citazione è vera: [words.py:57](/Users/eugenionerelli/dev/reflip/reflip/words.py:57) sceglie davvero «content word first», e `eligible` esiste già. Il ragionamento regge. La moneta di «four» si ri-lancia cambiando uno dei quattro token precedenti, quindi proteggere i fatti non costa copertura. È anche l'unica a distinguere la prova tolta dall'impronta che può restare (la perplessità bassa), e a vietare di tarare la riscrittura sui propri rilevatori. Limite: vale per le modifiche a slot, non per le 21 rotture della parafrasi.

**2. Il punto cieco più grande è di A.** Fa di reflip l'arbitro dei rilevatori e promette un «verdetto per chi giudica». Ma l'1% di falsi positivi è misurato su Wikipedia e giornali, non su studenti e non madrelingua, cioè su chi verrà accusato (C, E). Inoltre la regola di rifiuto in [PREREG.md:86](/Users/eugenionerelli/dev/reflip/docs/detect/PREREG.md:86) non guarda i falsi positivi della cella: su questo C ha ragione. L'audit di A misura poi una curva che non dipende né dal modello né dalla chiave. La quota intatta è (k-5)/k, cioè il 17% e il 50% già misurati. Da un modello all'altro cambia solo la lunghezza minima.

**3. Tutte e cinque leggono l'AI Act come un affare di Anthropic.** A scrive che l'art. 50 «obbliga ogni fornitore di un sistema che genera testo», ma non vede che reflip, con il suo parafrasatore, è uno di loro. L'esenzione open source dell'art. 2(12) non vale per i sistemi dell'art. 50 né per quelli ad alto rischio. Se la versione web mette in servizio il parafrasatore dal sito, può nascere l'obbligo di marcare le proprie riscritture. Un rilevatore offerto alle scuole può ricadere nell'allegato III, punto 3(d): rilevare comportamenti vietati degli studenti durante le prove. Decide la finalità dichiarata su sito e README, che va fissata prima del lancio. L'autorità competente è l'AESIA, non solo l'AEPD.

### Revisione 3

**1. La più forte è E**, perché attacca la causa e non il sintomo. L'ho verificato: `choose_slots` sceglie «content word first» ([words.py:57](/Users/eugenionerelli/dev/reflip/reflip/words.py:57)), e il parametro `eligible` esiste già per gli span protetti. Il meccanismo regge. La moneta di «four» si ri-lancia cambiando uno dei quattro token prima, quindi proteggere i fatti non costa copertura, tranne nelle finestre fatte solo di fatti. Costa un giorno, e il criterio decide in entrambi i sensi. Il limite: agisce sugli slot, e sulla parafrasi libera serve comunque la guardia di B. Seconda viene B, l'unica che ha contato i file e ha trovato un buco aperto nel protocollo.

**2. Il punto cieco più grande è di B.** La risposta più operativa propone come v1 web il solo rilevatore, cioè la parte che colpisce terzi. E lo spedirebbe con soglie tarate sul Mac e su prosa nativa curata. Le sue trappole sono tutte di rete. Non vede che con pesi quantizzati su WebGPU la soglia di coda si sposta (C). Non vede nemmeno gli studenti in seconda lingua, che saranno i falsi positivi veri (C, E). Se la si segue da sola, mette online un «1%» che in classe non vale.

**3. Tutte hanno mancato la letteratura.** A, B ed E fanno di reflip l'arbitro, la classifica, il banco. Accettano la premessa «nessuno pubblica numeri», che è vera per i quaranta siti ma falsa per la ricerca. RAID (Dugan et al., ACL 2024) è già un benchmark condiviso, con una classifica pubblica di rilevatori commerciali sotto attacchi di parafrasi. MarkMyWords (Piet et al., 2023) e MarkLLM (Pan et al., 2024) misurano già la robustezza dei watermark e il costo in qualità. Il repo non ne cita nessuno. Per essere citato (C, E), reflip deve agganciarsi lì, con le sue celle in italiano e spagnolo e con il proprio attacco. E deve scrivere il paper: l'autore è un dottorando.

### Revisione 4

**1. La più forte è E.** È l'unica risposta che riconduce le rotture di significato a una causa nel codice e propone una prova falsificabile da un giorno. L'ho verificato: `choose_slots` sceglie davvero "content word first" ed `eligible` esiste già ([words.py:57](/Users/eugenionerelli/dev/reflip/reflip/words.py:57)). Anche il ragionamento regge. La moneta di "four" si ri-lancia cambiando uno dei quattro token che lo precedono, quindi proteggere "four" non costa copertura. E copre inoltre i falsi positivi, l'"esito" e il divieto di tarare la riscrittura sui propri rilevatori. Il limite: la correzione vale per l'infill e per le riparazioni a slot, non per la parafrasi in sé (le 21 rotture). Lì serve la guardia di B. C fa la critica migliore, ma costruisce meno.

**2. Il punto cieco più grande è in A.** A vuole fare di reflip l'arbitro: "verdetto per chi giudica", linee guida degli atenei, scuole che analizzano i temi degli studenti. Non chiede mai su chi è misurato l'1% di falsi positivi. È misurato su Wikipedia e giornali, non su studenti né su non madrelingua (lo dicono C ed E, con Liang et al. 2023). Il timbro dell'arbitro finirebbe su accuse sbagliate. D ha lo stesso buco in piccolo: rende leggibile ("3 testi umani su 100") un numero che vale solo per la prosa di giornale.

**3. Che cosa hanno mancato tutte.** Prendono il "rumore" per verità, ma è il rumore dei rilevatori di reflip, media e media pesata ([README.md:51](/Users/eugenionerelli/dev/reflip/README.md:51)). Chi ha la chiave vede di più:
- il rilevatore bayesiano, che sta nello stesso rilascio di transformers, manca dal banco;
- se resta una quota di posizioni intatte, il segnale cresce con la radice della lunghezza e sommando tutti i testi di un account: l'1,8 di E diventa 3,5 su un testo quattro volte più lungo;
- con i propri log, il recupero per similarità ritrova le parafrasi (Krishna et al., NeurIPS 2023).

Il banco deve misurare per lunghezza e contro il rilevatore più forte. La pagina deve dire che la riscrittura sfugge al watermark, non a chi tiene i log.

### Revisione 5

**1. La più forte: E.** È l'unica che lega il limite più grave, le rotture sul testo denso, a una causa nel codice e a una prova falsificabile in un giorno. L'ho verificato: `choose_slots` sceglie «content word first» e ha già il parametro `eligible` ([words.py:57](/Users/eugenionerelli/dev/reflip/reflip/words.py:57)). Il meccanismo regge. La moneta di «four» si ri-lancia cambiando uno dei quattro token precedenti, quindi proteggere un fatto non costa copertura. E nomina anche la popolazione su cui si contano i falsi positivi (il corpus CAES), toglie «esito» e propone la prova a Wi-Fi spento. Ha un limite: `choose_slots` serve solo infill e hybrid ([llm.py:649](/Users/eugenionerelli/dev/reflip/reflip/transforms/llm.py:649)). La parafrasi riscrive il paragrafo intero e resta scoperta. C è il critico migliore (oracolo, potenza per cella, soglie in q4/q8), ma propone poco da costruire.

**2. Il punto cieco più grande: A.** Vuole fare di reflip «l'arbitro» per scuole e atenei. Però la soglia all'1% è misurata su Wikipedia e sui giornali, non sugli studenti e sui non madrelingua che verrebbero accusati (C, E). Mette verdetto e riscrittura sullo stesso motore e non vede l'oracolo che C segnala. È l'unica delle cinque che non nota il problema di «esito». Infine il cliente di `reflip audit` è un'ipotesi di mercato, non una misura.

**3. Che cosa hanno mancato tutte: la letteratura.** «Nessuno pubblica il prima e il dopo» vale per i quaranta remover, non per la ricerca:
- MarkMyWords (Piet et al., 2023) misura già quanto un watermark resiste alle manomissioni e quanto costa in qualità.
- RAID (Dugan et al., ACL 2024) tiene una classifica pubblica di rilevatori sotto attacco.
- AuTexTification (IberLEF 2023) copre lo spagnolo.

Prima di proporsi come banco di misura (A, B, E), reflip deve dire che cosa aggiunge: l'italiano, il calcolo sul dispositivo, il costo contato in fatti alterati.

C'è una seconda svista comune. [README.md:74](/Users/eugenionerelli/dev/reflip/README.md:74) dice che il tokenizer proxy ha "similar granularity" rispetto a quello di Claude e che la soglia "leaves margin". È il ponte fra le misure e Claude, e nel README non ha un numero.

## Il presidente

## Dove il consiglio concorda

- **Il valore di reflip è la misura, non la riscrittura.** Tutti e cinque ci arrivano per strade diverse. Il Pensatore ne fa il banco su cui si misura chiunque trasformi o giudichi un testo. L'Espansionista parla del «metro, non la gomma», il Bastian Contrario di «molto citato». Per l'Estraneo il prodotto è il prezzo mostrato su ogni testo, per l'Esecutore il lancio è un benchmark. Nessuno difende la vetrina del remover.
- **Il coseno 0,955 è il numero sbagliato.** È il segnale più forte del consiglio: cinque su cinque, ognuno per conto suo, chiedono la stessa colonna. Sono i fatti alterati (cifre, numeri in lettere, nomi propri, negazioni, quantificatori), contati per differenza meccanica, per 1.000 parole e per lingua. Un coseno misura l'argomento, e «four» diventato «five» non lo sposta.
- **«Esito» va tolto dalle statistiche.** Lo dicono quattro su cinque, tutti tranne l'Espansionista. Un verdetto è un bit calcolato sul testo, e un rifiuto per lunghezza rivela la lunghezza.
- **Il tasso di falsi positivi dipende dalla popolazione.** Lo dicono il Bastian Contrario e il Pensatore, e lo confermano tutte e cinque le revisioni. L'1% misurato su Wikipedia e sui giornali non vale per lo studente che scrive in seconda lingua, cioè per chi verrà accusato (Liang et al., 2023).
- **La privacy deve poterla verificare chi usa la pagina.** Il Pensatore propone la prova a rete staccata, l'Espansionista il registro di rete vuoto, l'Estraneo il payload esatto accanto al bottone, l'Esecutore il test headless.
- **Riscrittura e rilevatori non vanno chiusi in un ciclo.** Il Bastian Contrario ci vede un oracolo locale per l'attacco adattivo, il Pensatore due righelli che diventano uno, l'Estraneo un negozio di grimaldelli che vende anche serrature.
- **Il lancio che porta citazioni è la misura dei rimuovi-watermark esistenti.** Lo propongono Pensatore, Esecutore ed Espansionista, a partire da un dato che c'è già: togliere i caratteri invisibili non sposta lo z.
- **Niente promesse sul watermark di Claude.** L'Estraneo mostra che oggi il README lo lascia credere. L'Esecutore vuole che «rileva il watermark di Claude» non compaia nemmeno come «in arrivo».

## Dove il consiglio si scontra

**Che cosa mettere per primo nel browser.** L'Esecutore propone solo il rilevatore con la coppia da 0,5B: è leggero, mentre i 2,5 GB del riscrittore in una pagina non stanno. Il Bastian Contrario non vuole niente sul web prima di tre condizioni: un set umano in seconda lingua, il conteggio dei fatti rotti e la calibrazione sul file ONNX vero. L'Espansionista vuole il verdetto per chi giudica, proposto alle scuole come argomento di privacy. Il disaccordo nasce da che cosa si ottimizza. L'Esecutore guarda che cosa gira e che cosa si scarica, il Bastian Contrario e il Pensatore guardano chi paga un errore. Per il rilevatore non paga l'utente: paga uno studente.

**Togliere e rilevare sullo stesso motore.** Per l'Espansionista è la forza di reflip: tre uscite, e il doppio uso come credenziale da «penetration test del watermark». Anche il piano dell'autore mette le due funzioni nella stessa pagina. Per il Bastian Contrario, il Pensatore e l'Estraneo è il difetto. Hanno ragione entrambi, ma su piani diversi. Dentro un banco di misura le due metà si controllano a vicenda. Nell'interfaccia dell'utente finale diventano un umanizzatore.

**«Molto usato» o «molto citato».** Il Bastian Contrario e il Pensatore cambiano l'obiettivo: gli studenti usano chi promette, giornalisti e regolatori citano chi ha i numeri. L'Espansionista crede in un uso largo che non passa dal remover, attraverso il diff dei fatti. L'Estraneo avverte che se l'autore non nomina il suo utente lo nomineranno gli altri, e i limiti misurati disegnano una tesina in inglese.

**L'audit per chi marca.** L'Espansionista vede un cliente nuovo: chi deve marcare un modello aperto per l'art. 50. Due revisioni rispondono così:
- la curva «una modifica ogni k token» vale (k−5)/k con qualunque modello e chiave, e il 17% e il 50% sono già misurati;
- da un modello all'altro cambia quasi solo la lunghezza minima;
- il cliente è un'ipotesi di mercato.

**Da dove partire.** Il Pensatore partirebbe da un giorno di lavoro sulla scelta degli slot, l'Esecutore dalla chiusura della tabella del rilevamento. Il Bastian Contrario vuole prima le tre condizioni per il web, l'Espansionista `reflip audit`, l'Estraneo la prima schermata davanti a uno sconosciuto. Ognuno parte dal rischio che considera decisivo. Tutte e cinque le revisioni giudicano più forte la risposta del Pensatore.

## Punti ciechi emersi

- **La correzione del Pensatore non tocca la parafrasi.** L'ho verificato nel codice. `_plan_slots` serve l'infill ([llm.py:652](/Users/eugenionerelli/dev/reflip/reflip/transforms/llm.py:652)) e `hybrid` ([llm.py:831](/Users/eugenionerelli/dev/reflip/reflip/transforms/llm.py:831)), non `paraphrase` ([llm.py:786](/Users/eugenionerelli/dev/reflip/reflip/transforms/llm.py:786)). Scegliere meglio gli slot può ridurre le 32 rotture dell'infill. Per le 21 della parafrasi serve la guardia dell'Esecutore.
- **La letteratura esiste, e il repo non la cita.** «Nessuno pubblica il prima e il dopo» vale per i quaranta siti, non per la ricerca:
  - RAID (Dugan et al., ACL 2024) classifica i rilevatori sotto attacco;
  - MarkMyWords (Piet et al., 2023) e MarkLLM (Pan et al., 2024) misurano robustezza e costo dei watermark;
  - AuTexTification (IberLEF 2023) copre lo spagnolo.

  La nicchia di reflip va definita rispetto a questi lavori: italiano e spagnolo, testi brevi, rimuovi-watermark di consumo, costo contato in fatti, calcolo sul dispositivo. E l'autore, che è un dottorando, ha un paper da scrivere.
- **Il «rumore» è relativo ai rilevatori di reflip.** Il banco usa media e media pesata ([README.md:51](/Users/eugenionerelli/dev/reflip/README.md:51)) e non ha il rilevatore bayesiano di SynthID-Text. Le posizioni rimaste intatte producono un segnale residuo che cresce con la radice della lunghezza e si somma sui testi dello stesso autore. L'1,8 stimato dal Pensatore diventa 3,5 su un testo quattro volte più lungo. E chi conserva i log ritrova le parafrasi per similarità (Krishna et al., NeurIPS 2023).
- **reflip stesso può ricadere nell'art. 50.** L'esenzione open source dell'art. 2(12) non copre i sistemi dell'art. 50 né quelli ad alto rischio. Un riscrittore messo in servizio dal sito potrebbe dover marcare le proprie uscite. Un rilevatore proposto alle scuole può ricadere nell'allegato III, punto 3. Decide la finalità dichiarata, e l'autorità competente è anche l'AESIA, oltre all'AEPD.
- **Il collegamento con Claude non ha un numero.** [README.md:74](/Users/eugenionerelli/dev/reflip/README.md:74) dice che il tokenizer proxy ha «similar granularity» e che la soglia «leaves margin», senza misura. Eppure è l'unico passaggio fra i numeri di reflip e Claude. Se il tokenizer di Claude è più fine del proxy oltre il margine, una modifica ogni 6 token di Claude lascia intatto il 17% delle posizioni, e ogni 7 il 29%.
- **Un watermark in produzione forse si può misurare.** Google ha il portale SynthID Detector, con lista d'attesa per ricercatori, e Gemini marca il testo. Testi Gemini controllati prima e dopo reflip sarebbero l'unica riga misurata su un watermark vero. Se le condizioni d'uso lo vietano, va scritto anche questo.

## La raccomandazione

**Che cosa deve diventare.** reflip deve diventare il listino prezzi delle riscritture. Per ogni trasformazione pubblica due numeri misurati: quanto nasconde a ciascun rilevatore e quanto rompe di ciò che il testo dice. Il riscrittore resta come attacco di riferimento, il rilevatore come righello. La porta d'ingresso per il pubblico è il diff dei fatti. Serve a chiunque faccia riscrivere, tradurre o riassumere un testo da un modello, e non aiuta nessuno a ingannare.

**Sul «molto usato» la risposta è netta.** L'autore ha misurato da sé dove reflip funziona: prosa lunga, generica e in inglese, con pochi numeri e nessuna voce personale da salvare. Con questi limiti, un remover molto usato è un remover per tesine e articoli SEO, con il suo nome sopra. Non va inseguito. L'uso largo si cerca con il diff, le citazioni con il banco e con un paper. Che il diff porti davvero la folla è un'ipotesi dell'Espansionista. Le statistiche per funzione la verificano poche settimane dopo il lancio.

**Che cosa non deve fare:**
- presentarsi come remover;
- dare verdetti su persone o proporsi alle scuole;
- mettere riscrittura e rilevatore nello stesso ciclo, o tarare l'una sull'altro;
- promettere qualcosa sul watermark di Claude o di Gemini, che non può misurare;
- aggiungere lingue o rilevatori prima della tabella per cella.

**Rilevamento: in profondità, non in larghezza.**

*Il protocollo.* Prima del punteggio va emendato. La regola di rifiuto ([PREREG.md:86](/Users/eugenionerelli/dev/reflip/docs/detect/PREREG.md:86)) guarda l'AUROC e la metà dei testi di macchina, mai i falsi positivi della cella. La soglia nasce dagli umani delle tre lingue messi insieme ([PREREG.md:74](/Users/eugenionerelli/dev/reflip/docs/detect/PREREG.md:74)). Con 75 umani di prova per cella, anche zero falsi positivi certificano solo «sotto il 3,9%» (limite superiore al 95%, unilaterale). Per scrivere «1%» servono circa 300 umani di prova per cella e nessun errore. Gli umani sono la parte economica del corpus, quindi vanno portati a 300.

*Chi viene accusato.* Serve una popolazione separata di testi scritti in seconda lingua: il CAES per lo spagnolo, l'equivalente per inglese e italiano se le licenze lo permettono. Vanno inclusi anche gli stessi testi passati da un correttore, e il loro tasso di falsi positivi si riporta a parte.

*Che cosa vede l'utente.* Il rilevatore risponde «N testi umani su 100 di questa popolazione hanno avuto un punteggio così» (Estraneo). Niente probabilità con un prior del 50%, niente punteggio grezzo in prima riga. Il punteggio zero-shot non compare mai accanto a una riscrittura, né nell'app né nel JSON di `rewrite`. In prima pagina va invece dove cadono su Binoculars e Fast-DetectGPT i testi riscritti da reflip, qualunque sia il risultato. reflip toglie la prova, forse non l'impronta.

*Il rilevatore a chiave nota.* Resta il righello del banco, perché nessun utente ha una chiave. Va aggiunto il rilevatore bayesiano, con risultati per lunghezza. «Rumore» diventa «sotto soglia per i rilevatori media e media pesata, su testi di 144-420 token».

*Il browser e Google.* Il rilevatore va nel browser solo dopo tre cose: la tabella per cella, il set in seconda lingua e la calibrazione sul file e sul backend che la pagina serve davvero. Infine l'autore chieda l'accesso a SynthID Detector.

**Misura: il costo in fatti diventa il numero principale.** Un solo codice serve a quattro cose.
- `reflip diff` elenca cifre, numeri in lettere in italiano, spagnolo e inglese, nomi propri, negazioni e quantificatori cambiati, aggiunti o spariti. La sua fixture è il sommario da 575 parole con le rotture contate a mano.
- Dà la colonna «fatti alterati per 1.000 parole», per lingua, al posto del coseno nella tabella principale.
- Fa da guardia nella parafrasi (Esecutore).
- Fa da criterio per la scelta degli slot (Pensatore).

L'esperimento del Pensatore resta la migliore idea del consiglio. Se le rotture scendono verso zero a parità di copertura, il limite sul testo tecnico cade. Se le finestre fatte solo di fatti lasciano troppo z, almeno il prezzo è misurato. Lo z residuo va riportato per lunghezza.

Al collegamento con Claude serve un numero: il rapporto token/parola per lingua, misurato sugli stessi testi con il proxy e con il conteggio dei token dell'API Anthropic. Da lì ogni soglia mostrata all'utente si scrive in parole per lingua. Ogni modello offerto, ovunque, ha la sua riga. Niente 8B per salvare l'italiano: è già misurato che fa peggio.

**Privacy: meno campi, e una prova che chiunque può ripetere.**
- Le statistiche diventano uno schema chiuso a valori enumerati: evento, funzione, modello. Niente esito, durate, punteggi o lunghezze.
- Le capacità del dispositivo si leggono sul posto per scegliere il modello e non si spediscono. Spedirle ricade nell'art. 5(3) ePrivacy e nell'art. 22.2 LSSI.
- Il test confronta ogni payload con l'elenco delle chiavi e dei valori permessi. Cercare il testo nel payload non basta: quella ricerca non vede né una lunghezza né un verdetto.
- Un test headless verifica che durante l'elaborazione non parta nessuna richiesta e che la pagina funzioni a rete staccata.
- I pesi sono fissati per revisione e controllati per SHA-256 nella pagina, così una soglia vale per quel file preciso.
- La connect-src si prova su un download vero, perché Hugging Face rimanda su altri host. Il contatore sta su un Worker, perché GitHub Pages non riceve POST.
- La [riga 7 del README](/Users/eugenionerelli/dev/reflip/README.md:7) mette insieme «Nothing leaves your machine» e l'endpoint compatibile OpenAI. Vanno separati, e va scritto che con un endpoint remoto il testo esce.

**Prodotto: il prezzo su ogni testo, e la porta è il diff.**

*La v1 web.* Qui la mia scelta non coincide con nessuna delle cinque. La v1 web non è il rilevatore e non è il verdetto per le scuole: è il diff dei fatti in JavaScript, senza modello. Gira su un telefono e a rete staccata, e non ha doppio uso. Non solleva le domande dell'art. 50 né dell'allegato III. Dimostra la privacy in dieci secondi e misura se l'uso largo esiste.

*Il riscrittore resta fuori dal sito*, per quattro ragioni indipendenti: è il mercato più affollato e indifendibile, pesa 2,5 GB, i modelli più piccoli adatti al browser non sono misurati, e c'è il rischio dell'art. 50. Resta nella CLI e nell'app.

*La prima schermata.* In cima va la frase dell'Estraneo, poi la sua prova con uno sconosciuto e tre domande.

*Il lancio pubblico* è `reflip bench` sui rimuovi-watermark open source, collegati con adattatori, con z e fatti alterati e reflip nella stessa tabella. Va fatto solo dopo la colonna dei fatti, perché una classifica per solo z premia il rimuovi-watermark più aggressivo. Il corpus umano si pubblica come elenco di URL più script. Oggi `data/detect/` è escluso da git, e deve restarlo.

*Il resto:*
- la finalità dichiarata va in README e sito prima di qualunque lancio web;
- `reflip audit` non diventa un prodotto: la lunghezza minima diventa una sezione del banco;
- prima del lancio l'autore legga che cosa dicono i termini d'uso di Anthropic su chi aggira le marcature. Lo chiede il Bastian Contrario, e nessuna revisione l'ha ripreso. L'autore costruisce reflip con Claude Code e genera il corpus con Haiku: il rischio è perdere l'attrezzo con cui lavora.

**Dove dissento dalla maggioranza.** Le cinque revisioni mettono il Pensatore in testa, e sulla sostanza concordo. Ma il suo esperimento si può fare in qualunque giorno. L'emendamento al protocollo invece si può fare pulito solo prima di vedere i numeri, quindi viene prima.

## Cambi concreti a reflip, in ordine

1. [PREREG.md](/Users/eugenionerelli/dev/reflip/docs/detect/PREREG.md:86): nota datata prima del punteggio, con limite superiore dei falsi positivi per cella nella regola di rifiuto, 300 umani di prova per cella, seconda lingua a parte e le richieste lunghe in italiano che mancano.
2. [README.md](/Users/eugenionerelli/dev/reflip/README.md): in prima riga «Nessuno fuori da Anthropic può dirti se il tuo testo di Claude è ancora marcato, nemmeno reflip», e alla riga 7 l'endpoint remoto separato dalla promessa.
3. Sito: v1 con il solo diff in JavaScript; il riscrittore resta in CLI e app; il rilevatore arriva dopo tabella per cella, set in seconda lingua e calibrazione sul file servito.
4. Statistiche: schema chiuso con evento, funzione e modello, senza esito, durate, punteggi, lunghezze né capacità del dispositivo, con un test a elenco di valori permessi.
5. `reflip diff`: cifre, numeri in lettere nelle tre lingue, nomi, negazioni e quantificatori cambiati, in JSON, con il sommario da 575 parole come fixture.
6. README: «fatti alterati per 1.000 parole» per lingua al posto del coseno nella tabella principale; il coseno resta nella tabella completa come vicinanza di argomento.
7. `paraphrase` ([llm.py:786](/Users/eugenionerelli/dev/reflip/reflip/transforms/llm.py:786)): guardia su nomi e numeri, una nuova richiesta del paragrafo, poi `{"ok": false}`; nel README quante rotture della fixture le sfuggono.
8. `choose_slots` ([words.py:57](/Users/eugenionerelli/dev/reflip/reflip/words.py:57)): fatti fuori da `eligible`, parole funzionali e punteggiatura per prime, poi rilancio sui 24 testi e sul sommario con lo z residuo per lunghezza.
9. README e sito: finalità dichiarata come misura di trasformazioni del testo, non decisioni su persone né valutazione di studenti.
10. Pagina web: test headless senza richieste durante l'elaborazione, prova a rete staccata e payload esatto accanto al bottone.
11. Pesi del browser fissati per revisione e SHA-256, una soglia per ogni coppia di file e backend, connect-src provata su un download vero.
12. CLI: rifiuto sotto la lunghezza minima espressa in parole per lingua, rilevatore che risponde «N testi umani su 100», nessun punteggio zero-shot nell'output di `rewrite`.
13. Banco: rilevatore bayesiano, risultati per lunghezza e «sotto soglia per media e media pesata» al posto di «rumore».
14. [README.md:74](/Users/eugenionerelli/dev/reflip/README.md:74): rapporto token/parola per lingua, misurato con il proxy e con il conteggio dei token dell'API Anthropic.
15. Prima pagina: dove cadono su Binoculars e Fast-DetectGPT i testi riscritti da reflip.
16. App: originale e riscrittura affiancati, con i fatti alterati evidenziati.
17. `reflip bench` con adattatori per i rimuovi-watermark open source, colonne z e fatti alterati, reflip incluso, corpus umano pubblicato come URL più script.
18. README: sezione sui lavori correlati (RAID, MarkMyWords, MarkLLM, AuTexTification, Krishna et al.).
19. Pacchetto PyPI.

## La prima cosa da fare

Adesso, prima che parta il punteggio, committa in [PREREG.md](/Users/eugenionerelli/dev/reflip/docs/detect/PREREG.md:86) una nota datata con tre cambi:
- la regola di rifiuto delle righe 86-89 guarda anche il limite superiore al 95% dei falsi positivi di ogni cella;
- gli umani di prova salgono a 300 per cella;
- i testi scritti in seconda lingua diventano una popolazione separata.

È l'unico passo che dopo non si può più fare pulito. `data/detect/ai.jsonl` ha già 305 testi di macchina su 360 e in `data/results/` il rilevamento non c'è ancora. Appena compare un numero per cella, ogni modifica diventa post-visione.
