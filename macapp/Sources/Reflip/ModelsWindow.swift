import AppKit
import SwiftUI

/// The window where a person chooses, downloads and judges the model reflip rewrites
/// with.
///
/// A window of its own, opened from the server strip or the Rewrite menu, not a sheet on
/// the main one: a 2.5 to 14 GB download can run for minutes, and a person should be able
/// to keep pasting text into the main window while it does. It shares nothing live with
/// that window's `ServerStore`; the two agree on which model is "in use" through
/// `Cli.model`, the same persisted setting the Settings window already reads and writes,
/// and a choice made here reaches the main window's picker through the same
/// `NotificationCenter` post the menu commands already use, not through a reference
/// passed between two independent windows.
///
/// Three sections, and nothing about which models exist is compiled into this file. "On
/// this Mac" and the default model come from `reflip server status`; the catalogue comes
/// from `reflip models --recommended`; the search results come from Hugging Face by way
/// of `reflip models --search`. A build of this window from before some model existed
/// still shows it, because it never had to know the name in advance.
struct ModelsWindow: View {
    @StateObject private var store = ModelsStore()

    var body: some View {
        List {
            Section("On this Mac") { onThisMacSection }
            Section("Worth trying") { worthTryingSection }
            Section("Search Hugging Face") { searchSection }
        }
        .listStyle(.inset)
        // Each section's rows arrive from its own subprocess call and land at a
        // slightly different moment; an animated insert for that is motion nobody
        // asked to watch rather than useful feedback.
        .transaction { $0.disablesAnimations = true }
        .frame(minWidth: 700, idealWidth: 820, minHeight: 480, idealHeight: 680)
        .onAppear {
            Task { await store.loadInstalled() }
            Task { await store.loadRecommended() }
            // Quitting has to take this window's children with it too, the same reason
            // `ContentView` does this for the rewrite and the server strip: a terminated
            // app must not leave a download or a measurement's model resident with no
            // window left to say what is using the machine. Appended rather than
            // assigned, because the main window already owns the one `onQuit` slot.
            //
            // Captured weakly: this window can be closed and reopened many times in one
            // session, each time with a fresh `ModelsStore`, and a strong capture here
            // would have kept every earlier one alive for the life of the app, holding
            // its `Process` references long after `onDisappear` had already cleaned
            // them up.
            AppDelegate.onQuitHandlers.append { [weak store] in store?.terminateChildren() }
        }
        .onDisappear { store.terminateChildren() }
    }

    // MARK: - on this Mac

    private var onThisMacSection: some View {
        Group {
            if store.isLoadingInstalled && store.installed.isEmpty {
                ProgressView().controlSize(.small)
            } else if let problem = store.installedProblem {
                Text(problem).font(.callout).foregroundStyle(.red)
            } else if store.installed.isEmpty {
                Text("Nothing is downloaded yet. Pick something from Worth trying below, "
                     + "or search Hugging Face for anything published as a GGUF file.")
                    .font(.callout)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            } else {
                ForEach(store.installed) { model in
                    InstalledRow(model: model, inUse: store.isInUse(model.name)) {
                        Cli.model = model.name
                        NotificationCenter.default.post(name: .reflipModelChosen,
                                                        object: model.name)
                    }
                    // A ref like "qwen3:8b" names both an installed model here and a
                    // catalogue entry below, and `List` was found to reuse a row's
                    // rendered content across sections when two `ForEach`s produced the
                    // same `Identifiable.id`: this window's "On this Mac" section
                    // showed catalogue sentences and a Measure it button for exactly
                    // the models that were also in the catalogue. The `.id()` below is
                    // the fix, not decoration: it gives every row in this List a
                    // section-qualified identity so nothing downstream of `Identifiable`
                    // can collide across the three lists again.
                    .id("installed-\(model.name)")
                }
            }
        }
    }

    // MARK: - worth trying

    private var worthTryingSection: some View {
        Group {
            if store.isLoadingRecommended && store.recommended == nil {
                ProgressView().controlSize(.small)
            } else if let problem = store.recommendedProblem {
                Text(problem).font(.callout).foregroundStyle(.red)
            } else if let recommended = store.recommended {
                // reflip's own sentence for why the server itself could not be read.
                // The catalogue is still worth showing without it, so this is a note
                // above the rows rather than a reason to hide them.
                if let reason = recommended.serverReason {
                    Text(reason)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                ForEach(recommended.recommended) { model in
                    CatalogueRow(model: model, store: store)
                        // See the matching comment in `onThisMacSection`: this section
                        // qualifies its identity too, since a ref here can equal an
                        // installed model's name above.
                        .id("catalogue-\(model.ref)")
                }
            } else {
                Text("Asking reflip for the catalogue.")
                    .font(.callout)
                    .foregroundStyle(.secondary)
            }
        }
    }

    // MARK: - search Hugging Face

    private var searchSection: some View {
        Group {
            HStack {
                TextField("Search by model name", text: $store.query)
                    .textFieldStyle(.roundedBorder)
                    .onSubmit { Task { await store.runSearch() } }
                Button("Search") { Task { await store.runSearch() } }
                    .disabled(store.query.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                              || store.isSearching)
            }
            .padding(.vertical, 2)

            if store.isSearching {
                ProgressView().controlSize(.small)
            }
            if let problem = store.searchProblem {
                Text(problem).font(.callout).foregroundStyle(.red)
            }
            if let search = store.search {
                if let note = search.note {
                    Text(note)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                if search.results.isEmpty && !store.isSearching {
                    Text("Nothing came back for that search.")
                        .font(.callout)
                        .foregroundStyle(.secondary)
                } else {
                    ForEach(search.results) { result in
                        SearchRow(result: result, store: store)
                            // Same reasoning as the other two sections: a search hit's
                            // ref could in principle equal a catalogue ref or an
                            // installed name, and this is cheap insurance against it.
                            .id("search-\(result.ref)")
                    }
                }
            } else if !store.isSearching {
                Text("Search for a model by name. Results come straight from Hugging "
                     + "Face and are not recommendations.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
    }
}

// MARK: - one row for what is already downloaded

private struct InstalledRow: View {
    let model: InstalledModel
    let inUse: Bool
    let onUse: () -> Void

    var body: some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: 6) {
                    Text(model.name).font(.body.weight(.medium))
                    if inUse {
                        Label("In use", systemImage: "checkmark.circle.fill")
                            .labelStyle(.titleAndIcon)
                            .font(.caption)
                            .foregroundStyle(.green)
                    }
                }
                Text(Format.bytes(model.size))
                    .font(.caption)
                    .monospacedDigit()
                    .foregroundStyle(.secondary)
            }
            Spacer()
            if !inUse {
                Button("Use this one") { onUse() }
                    .help("Rewrite with this model from now on, in this window and the "
                          + "main one.")
            }
        }
        .padding(.vertical, 2)
    }
}

// MARK: - one row of the catalogue

private struct CatalogueRow: View {
    let model: CatalogueModel
    @ObservedObject var store: ModelsStore

    private var isDownloading: Bool { store.isPulling && store.pullingRef == model.ref }
    private var isMeasuringThis: Bool { store.isMeasuring && store.measuringRef == model.ref }
    private var result: MeasureResult? { store.measurements[model.ref] }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(alignment: .firstTextBaseline) {
                Text(model.ref)
                    .font(.body.weight(.medium))
                    .textSelection(.enabled)
                Spacer()
                Text(model.installed ? "Downloaded" : Format.gigabytes(model.sizeGB))
                    .font(.caption)
                    .monospacedDigit()
                    .foregroundStyle(.secondary)
            }
            Text("\(model.params) parameters. \(model.languages).")
                .font(.caption)
                .foregroundStyle(.secondary)

            // The two sentences reflip wrote about this model: what it is good at in the
            // window's ordinary text colour, and what to watch out for in secondary
            // colour, so the two never read as equally weighted.
            Text(model.goodAt)
                .font(.callout)
                .fixedSize(horizontal: false, vertical: true)
            Text(model.watchOut)
                .font(.callout)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)

            if model.watermarks {
                Label("This model watermarks its own output, so it is refused as a "
                      + "rewriter rather than offered.", systemImage: "xmark.seal.fill")
                    .font(.caption)
                    .foregroundStyle(.red)
                    .fixedSize(horizontal: false, vertical: true)
            }

            // A measured claim and an opinion must not look alike: this is the one line
            // in the row that came out of a real run rather than out of somebody's
            // judgement, marked with its own colour and icon for exactly that reason.
            if let measured = model.measured {
                Label(measured, systemImage: "checkmark.seal.fill")
                    .font(.caption)
                    .foregroundStyle(.green)
                    .fixedSize(horizontal: false, vertical: true)
                    .help("A real measurement on somebody's machine, reproducible with "
                          + "the Measure it button below, not an opinion.")
            }

            HStack(spacing: 10) {
                if !model.installed {
                    Button("Download") { store.download(model.ref) }
                        .disabled(store.isPulling || model.watermarks)
                        .help("Runs reflip pull \(model.ref) and downloads it into the "
                              + "local model server.")
                }
                Button(isMeasuringThis ? "Measuring…" : "Measure it") {
                    store.measure(model.ref)
                }
                .disabled(store.isMeasuring || model.watermarks)
                .help("Runs this model over watermarked texts from the benchmark corpus "
                      + "and reports what the detector said before and after. Spends "
                      + "real calls to the model.")
                Spacer()
            }

            if isDownloading {
                PullRow(pull: store.pull) { store.cancelDownload() }
            }
            if isMeasuringThis {
                RunProgress(live: store.measureLive)
            }
            if let result {
                MeasureFigures(result: result)
            }
        }
        .padding(.vertical, 4)
    }
}

// MARK: - one row of a Hugging Face search result

private struct SearchRow: View {
    let result: SearchResult
    @ObservedObject var store: ModelsStore

    private var isDownloading: Bool { store.isPulling && store.pullingRef == result.ref }
    private var refused: Bool { result.refused != nil }

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(alignment: .firstTextBaseline) {
                Text(result.repo)
                    .font(.body.weight(.medium))
                    .textSelection(.enabled)
                Spacer()
                Text(result.downloads == 1 ? "1 download" : "\(Format.count(result.downloads)) downloads")
                    .font(.caption)
                    .monospacedDigit()
                    .foregroundStyle(.secondary)
            }

            if let refused = result.refused {
                Text(refused)
                    .font(.callout)
                    .foregroundStyle(.red)
                    .fixedSize(horizontal: false, vertical: true)
            } else {
                if result.gated {
                    Text("Gated: Hugging Face requires approval before this can be "
                         + "downloaded.")
                        .font(.caption)
                        .foregroundStyle(.orange)
                }
                HStack(spacing: 10) {
                    Button("Download") { store.download(result.ref) }
                        .disabled(store.isPulling)
                    Button("Open the page") { openPage() }
                    Spacer()
                }
                if isDownloading {
                    PullRow(pull: store.pull) { store.cancelDownload() }
                }
            }
        }
        .padding(.vertical, 2)
        // Greyed with the sentence and no button, per the brief: a refused result reads
        // at a glance as not worth the same attention as the ones offered.
        .opacity(refused ? 0.6 : 1)
    }

    private func openPage() {
        guard let url = URL(string: result.page) else { return }
        NSWorkspace.shared.open(url)
    }
}

// MARK: - what a measurement left in the row

private struct MeasureFigures: View {
    let result: MeasureResult

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            if result.ok {
                if let verdict = result.verdict {
                    Text(verdict)
                        .font(.callout)
                        .fixedSize(horizontal: false, vertical: true)
                }
                HStack(alignment: .firstTextBaseline, spacing: 18) {
                    if let zBefore = result.zBefore {
                        figure(Format.zScore(zBefore), "detector z before")
                            .help("How far the original watermarked text stood out to "
                                  + "the detector, in standard deviations above chance. "
                                  + "Above 4 is a confident detection.")
                    }
                    if let zAfter = result.zAfter {
                        figure(Format.zScore(zAfter), "detector z after",
                              tint: zAfter < 4 ? .green : .orange)
                            .help("The same score after this model rewrote the text. "
                                  + "Below 4 means the detector can no longer tell the "
                                  + "result apart from unwatermarked text.")
                    }
                    if let coverage = result.coverage {
                        figure(Format.percent(coverage), "detector windows edited")
                            .help("The share of five-token windows the detector checks "
                                  + "that contain at least one edited word.")
                    }
                    if let seconds = result.seconds {
                        figure(Format.seconds(seconds), "seconds per text")
                            .help("How long this model took to rewrite one text on this "
                                  + "Mac.")
                    }
                    if let tokens = result.tokensPer1kWords {
                        figure(Format.count(Int(tokens.rounded())), "tokens per 1,000 words")
                            .help("How many tokens this model spent, per 1,000 words of "
                                  + "input. More tokens costs more time, and on a paid "
                                  + "API more money.")
                    }
                }
                if let samples = result.samples {
                    let errors = result.errors ?? 0
                    Text(errors > 0
                        ? "Measured on \(samples) text\(samples == 1 ? "" : "s"), \(errors) failed."
                        : "Measured on \(samples) text\(samples == 1 ? "" : "s").")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
            } else {
                Text(result.reason ?? "The measurement failed and reflip said nothing "
                     + "about why.")
                    .font(.callout)
                    .foregroundStyle(.red)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(.top, 2)
    }

    private func figure(_ value: String, _ caption: String,
                        tint: Color = .primary) -> some View {
        VStack(alignment: .leading, spacing: 1) {
            Text(value)
                .font(.callout.weight(.semibold))
                .monospacedDigit()
                .foregroundStyle(tint)
            Text(caption)
                .font(.caption2)
                .foregroundStyle(.secondary)
        }
        .accessibilityElement(children: .combine)
    }
}
