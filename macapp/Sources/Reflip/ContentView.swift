import AppKit
import SwiftUI

/// The window.
///
/// One column, read top to bottom: whether the model server is up, the text going in,
/// what to do to it, the text coming out, and what it cost. There is no list to browse
/// and nothing to select, so there is no sidebar; a split view here would be two panes
/// of which one is always empty.
///
/// Nothing in this window rewrites anything. Every button is a `reflip` command a
/// person could have typed, and every sentence on screen is a string that command
/// printed. The one exception is the empty state at the bottom, which has to say
/// something before reflip has been asked anything.
struct ContentView: View {
    @StateObject private var server = ServerStore()
    @StateObject private var rewriter = Rewriter()
    @Environment(\.openWindow) private var openWindow

    @State private var source = ""
    // The four names this window has always offered, so the picker has something to
    // show in the instant before `TransformCatalogue.fetch()` answers, and everything
    // it has ever offered if that command cannot be run at all. `reflip transforms` is
    // asked once, on appear, and replaces this list with whatever it says, `hybrid`
    // included: see `TransformCatalogue` for why the list itself is never compiled in.
    @State private var transformNames = ["paraphrase", "infill", "rules", "unicode"]
    /// The full path and sentence for any of a person's own transform files in
    /// `~/.reflip/transforms` that failed to load. Empty on every machine that has none
    /// of its own, which is almost every machine.
    @State private var transformLoadErrors: [String] = []
    @State private var transform = "paraphrase"
    @State private var stride = 3
    @State private var checkCoverage = true
    @State private var model = Cli.model
    @State private var saveProblem: String?

    /// The strip is refreshed every three seconds. Somebody can start Ollama from a
    /// terminal, stop it, or have the model unloaded under them, and none of that
    /// arrives as a notification: a window that only refreshed on its own actions would
    /// go on saying the server is up for as long as you looked at it.
    private let tick = Timer.publish(every: 3, on: .main, in: .common).autoconnect()

    var body: some View {
        VStack(spacing: 0) {
            ServerStrip(store: server, model: $model,
                        onStart: { Task { await server.start() } },
                        onStop: { Task { await server.stop() } },
                        onDownload: { server.download(chosenModel) })
            middle
            ReceiptStrip(receipt: rewriter.receipt)
        }
        .frame(minWidth: 620, minHeight: 620)
        .onAppear {
            server.reload()
            // Quitting has to take the children with it. Appended rather than assigned:
            // the Models window appends its own closure here too when it is open, and
            // the two must not overwrite each other.
            let engine = rewriter
            let strip = server
            AppDelegate.onQuitHandlers.append {
                engine.terminateChild()
                strip.terminateChild()
            }
            Task {
                let (names, errors) = await TransformCatalogue.fetch()
                transformNames = names
                transformLoadErrors = errors
                // The chosen transform might not be in the fresh list on the very first
                // launch of a build that renamed one; falling back to the first name
                // keeps the picker's selection inside its own list of choices.
                if !names.contains(transform), let first = names.first { transform = first }
            }
            Shot.arrange(rewriter: rewriter, source: $source)
            // `--shot-models` asks for a picture of the Models window instead of this
            // one, opened the same way the strip's own button opens it rather than by
            // any shortcut around `openWindow`. Bringing it forward is a second step
            // because opening it left the main window key in a launch started by
            // `open` rather than by a click.
            if Shot.wantsModelsWindow {
                openWindow(id: "models")
                Task { await Shot.bringModelsWindowForward() }
            }
        }
        .onReceive(tick) { _ in server.reload() }
        .onReceive(NotificationCenter.default.publisher(
            for: NSApplication.didBecomeActiveNotification)) { _ in server.reload() }
        .onReceive(NotificationCenter.default.publisher(for: .reflipRefresh)) { _ in
            server.reload()
        }
        .onReceive(NotificationCenter.default.publisher(for: .reflipRewrite)) { _ in
            start()
        }
        .onReceive(NotificationCenter.default.publisher(for: .reflipStop)) { _ in
            rewriter.cancel()
        }
        // The Models window posts this when "Use this one" is pressed there. The two
        // windows share no live object, so this is the only way a choice made in one
        // reaches the picker in the other.
        .onReceive(NotificationCenter.default.publisher(for: .reflipModelChosen)) { note in
            if let chosen = note.object as? String, !chosen.isEmpty { model = chosen }
        }
        .onChange(of: server.status) { _, fresh in
            // The picker starts on whatever reflip would have chosen for itself.
            // Spelling a model name in the window would freeze the recommended
            // rewriter into it, and the recommendation is a measured result that moves.
            if model.isEmpty, let fresh, !fresh.model.isEmpty { model = fresh.model }
        }
        .onChange(of: model) { _, value in Cli.model = value }
    }

    // MARK: - the column

    private var middle: some View {
        VStack(alignment: .leading, spacing: 12) {
            sourceSection
            controls
            if rewriter.isRunning {
                RunProgress(live: rewriter.live)
            }
            if let trouble {
                Label(trouble, systemImage: "exclamationmark.triangle.fill")
                    .font(.callout)
                    .foregroundStyle(.orange)
                    .fixedSize(horizontal: false, vertical: true)
            }
            resultSection
        }
        .padding(16)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
    }

    private var sourceSection: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text("Text to rewrite")
                    .font(.headline)
                Spacer()
                Text(wordCount == 1 ? "1 word" : "\(Format.count(wordCount)) words")
                    .font(.caption)
                    .monospacedDigit()
                    .foregroundStyle(.secondary)
                Button("Paste") { paste() }
            }
            editor(text: $source, placeholder: "Paste or type the text to rewrite here.")
        }
    }

    private var resultSection: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text("Result")
                    .font(.headline)
                Spacer()
                Button("Copy") { copy() }
                    .disabled(rewriter.text.isEmpty)
                Button("Save as...") { save() }
                    .disabled(rewriter.text.isEmpty)
            }
            // Read-only, and still selectable. A disabled TextEditor cannot be
            // selected at all, and taking the text away is the whole point of the
            // panel: the setter is dropped instead, so typing into it changes nothing.
            editor(text: Binding(get: { rewriter.text }, set: { _ in }),
                  placeholder: "The rewritten text will appear here.")
        }
    }

    /// The transform, then the two things that qualify it and the button.
    ///
    /// Two rows rather than one. The transform labels are sentences saying what will
    /// happen to the text, and at this window's width a sentence, a stepper, a checkbox
    /// and a button on one line truncated the sentence, which is the part that explains
    /// the choice.
    private var controls: some View {
        VStack(alignment: .leading, spacing: 8) {
            Picker("Transform", selection: $transform) {
                ForEach(transformNames, id: \.self) { name in
                    Text(TransformCatalogue.label(for: name)).tag(name)
                }
            }
            .labelsHidden()
            .frame(maxWidth: .infinity, alignment: .leading)

            // A file in this person's own `~/.reflip/transforms` that did not load,
            // reported here because the picker right above it is the one place on
            // screen already talking about which transforms exist. Silence about it
            // would look exactly like a transform they never wrote.
            ForEach(transformLoadErrors, id: \.self) { error in
                Label(error, systemImage: "exclamationmark.triangle.fill")
                    .font(.caption)
                    .foregroundStyle(.orange)
                    .fixedSize(horizontal: false, vertical: true)
            }

            HStack(spacing: 16) {
                Stepper(value: $stride, in: 2...10) {
                    Text("One edit every \(stride) words")
                        .monospacedDigit()
                        .foregroundStyle(TransformCatalogue.takesStride(transform)
                                         ? .primary : .secondary)
                }
                .disabled(!TransformCatalogue.takesStride(transform))
                .fixedSize()

                Toggle("Check the coverage", isOn: $checkCoverage)
                    .toggleStyle(.checkbox)

                Spacer(minLength: 8)

                if rewriter.isRunning {
                    Button("Stop") { rewriter.cancel() }
                        .keyboardShortcut(".", modifiers: .command)
                } else {
                    Button("Rewrite it") { start() }
                        .buttonStyle(.borderedProminent)
                        .keyboardShortcut("r", modifiers: [.command, .shift])
                        .disabled(!canRewrite)
                        .help(canRewrite ? "Send the text above to reflip and show what "
                              + "comes back."
                              : "Paste or type some text above first.")
                }
            }
        }
    }

    /// `TextEditor` has no placeholder of its own, so the first thing a first-time user
    /// saw in either box was a blank rectangle with no hint that anything belonged in
    /// it. The placeholder is drawn behind the editor rather than as its content, so it
    /// can never be selected, copied or mistaken for real text.
    private func editor(text: Binding<String>, placeholder: String) -> some View {
        ZStack(alignment: .topLeading) {
            if text.wrappedValue.isEmpty {
                Text(placeholder)
                    .font(.body)
                    .foregroundStyle(.tertiary)
                    .padding(.horizontal, 11)
                    .padding(.vertical, 14)
                    .allowsHitTesting(false)
            }
            TextEditor(text: text)
                .font(.body)
                .scrollContentBackground(.hidden)
                .padding(6)
        }
        .background(RoundedRectangle(cornerRadius: 6)
            .fill(Color(nsColor: .textBackgroundColor)))
        .overlay(RoundedRectangle(cornerRadius: 6)
            .strokeBorder(Color.secondary.opacity(0.25)))
        .frame(minHeight: 140, maxHeight: .infinity)
    }

    // MARK: - what the window knows about itself

    private var wordCount: Int {
        source.split(whereSeparator: \.isWhitespace).count
    }

    private var chosenModel: String {
        model.isEmpty ? (server.status?.model ?? "") : model
    }

    private var canRewrite: Bool {
        !source.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    /// One line for whatever went wrong last, whether that was reflip or this window
    /// failing to write a file. Two rows for two rare states is two empty rows for the
    /// rest of the time.
    private var trouble: String? {
        for candidate in [rewriter.errorText, saveProblem] {
            if let candidate, !candidate.isEmpty { return candidate }
        }
        return nil
    }

    // MARK: - the four things a person can press

    private func start() {
        guard canRewrite, !rewriter.isRunning else { return }
        saveProblem = nil
        rewriter.rewrite(text: source, transform: transform, stride: stride,
                         model: chosenModel, checkCoverage: checkCoverage)
    }

    private func paste() {
        guard let text = NSPasteboard.general.string(forType: .string) else { return }
        source = text
    }

    private func copy() {
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(rewriter.text, forType: .string)
    }

    private func save() {
        let panel = NSSavePanel()
        panel.nameFieldStringValue = "rewritten.md"
        panel.canCreateDirectories = true
        guard panel.runModal() == .OK, let url = panel.url else { return }
        do {
            try rewriter.text.write(to: url, atomically: true, encoding: .utf8)
            saveProblem = nil
        } catch {
            saveProblem = "Could not write that file: \(error.localizedDescription)"
        }
    }
}

/// The bar and the sentence under it while a rewrite runs.
///
/// Its own view because it observes the fast-moving object. Reading those fields in the
/// window's own body would rebuild both text editors on every tick, and one of them has
/// somebody's cursor in it.
struct RunProgress: View {
    @ObservedObject var live: RunState

    var body: some View {
        HStack(spacing: 10) {
            if let progress = live.progress {
                ProgressView(value: progress)
                    .frame(width: 160)
            } else {
                ProgressView()
                    .controlSize(.small)
            }
            VStack(alignment: .leading, spacing: 1) {
                Text(sentence)
                    .font(.callout)
                if !live.lastLine.isEmpty {
                    Text(live.lastLine)
                        .font(.system(.caption, design: .monospaced))
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }
            }
            Spacer()
        }
    }

    /// reflip's sentence for what it is doing, and its phase when it has not written a
    /// sentence yet. Nothing here is composed from the two.
    private var sentence: String {
        if !live.note.isEmpty { return live.note }
        return live.phase
    }
}
