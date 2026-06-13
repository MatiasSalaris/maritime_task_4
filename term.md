# Terminologia essenziale

Questa demo usa alcuni concetti marittimi minimi per rendere credibile lo scenario, ma non e' un sistema operativo reale ne' uno strumento di ingaggio.

## Termini necessari

**Asset / vehicle**
Un mezzo autonomo della squadra. Nella demo ci sono tre asset: due USV e un UAV.

**USV**
Unmanned Surface Vehicle: mezzo di superficie senza equipaggio. Nella mappa e' una piattaforma navale.

**UAV**
Unmanned Aerial Vehicle: mezzo aereo senza equipaggio. Nella mappa e' il drone.

**Mission**
L'ordine scritto in linguaggio naturale dall'utente. Gli agenti devono interpretarlo, dividersi i compiti e adattarsi se cambia durante l'esecuzione.

**Change of intent**
Cambio missione mentre la simulazione e' gia' in corso. E' uno dei requisiti della traccia: il gruppo deve riorganizzarsi senza restart.

**Contact**
Qualsiasi nave o oggetto rilevabile nel mondo simulato. Puo' essere traffico normale o un contatto da investigare.

**AIS**
Automatic Identification System: sistema con cui una nave trasmette identita', posizione, rotta e velocita'. Nella demo serve solo come indizio: una nave con AIS coerente e' normalmente meno sospetta.

**Commercial vessel**
Nave commerciale con profilo AIS regolare. In genere va monitorata, non inseguita.

**Fishing vessel**
Peschereccio con profilo AIS regolare. In genere va monitorato, non inseguito.

**Suspicious vessel**
Contatto senza identita' AIS chiara o marcato come anomalo nello scenario. E' il caso che gli agenti dovrebbero segnalare, identificare e, se richiesto dalla missione, seguire a distanza.

**Detected**
Il contatto e' dentro il raggio sensore di almeno un asset.

**Last seen**
Il contatto era stato visto, ma ora non e' piu' dentro il raggio sensore. La mappa mostra l'ultima posizione nota.

**Shared situational picture**
La vista comune costruita dagli agenti scambiandosi osservazioni e messaggi: chi vede cosa, quali contatti sono noti, chi sta coprendo quale area.

**P2P message**
Messaggio peer-to-peer tra agenti. Serve a coordinarsi senza un comandante centrale: proposal, ack, objection, handoff, report.

**Proposal**
Un agente propone un compito o una divisione dell'area.

**Ack**
Acknowledgement: un agente conferma di aver ricevuto e accettato una proposta o un handoff.

**Objection**
Un agente contesta una proposta e propone un'alternativa.

**Handoff**
Passaggio di responsabilita': un agente lascia un compito a un altro, per esempio il monitoraggio di una nave sospetta.

**Report**
Segnalazione strutturata di un contatto o di un'anomalia.

**Reasoning**
Spiegazione breve del perche' un agente ha scelto una certa azione. La traccia chiede che sia visibile, non nascosta nei log.

## Termini interni da non mostrare nella UI

**MMSI**
Identificativo numerico AIS di una nave. Utile internamente, ma troppo tecnico per la demo.

**c001, c002, c003...**
ID tecnici dei contatti sintetici nello scenario. Nella UI e' meglio mostrare "Commercial vessel", "Fishing vessel" o "Suspicious vessel".

**flagged**
Boolean interno che indica che il simulatore considera un contatto sospetto.

**TGT-001 / AIS-001 / UNK-001**
ID tecnici di tracciamento. Non sono necessari per la traccia e "TGT" puo' dare l'impressione sbagliata di targeting. Nella UI e' meglio usare etichette come "Suspicious 01" o "Vessel 02".

**active / ghost / unknown**
Stati tecnici del backend. Nella UI vanno resi come "Detected", "Last seen", "Not detected".

## Cosa richiede davvero la traccia

La traccia richiede tre agenti autonomi guidati da LLM, missione in linguaggio naturale, reasoning visibile, messaggi peer-to-peer, vista situazionale condivisa e adattamento a un cambio missione. Richiede contatti sintetici o reali con posizione e label comportamentale, ma non richiede di esporre gergo come MMSI, TGT o flagged nella UI.
