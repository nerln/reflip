import Foundation
import SwiftUI

/// The part of a rewrite that changes several times a second.
///
/// Kept off the Rewriter on purpose. When the phase and the fraction lived there, every
/// publish rebuilt everything observing it, which was the whole window: two text
/// editors, the server strip and the receipt, four times a second, for as long as the
/// rewrite ran. Only the small view that draws progress observes this one.
@MainActor
final class RunState: ObservableObject {
    /// reflip's own name for the stage, and its own sentence for what it is doing.
    /// Both are rendered as they arrive; neither is written here.
    @Published var phase = ""
    @Published var note = ""
    @Published var progress: Double?
    /// The last line that was not one of reflip's events, shown small under the bar.
    @Published var lastLine = ""

    func reset() {
        phase = ""
        note = ""
        progress = nil
        lastLine = ""
    }
}

/// Running one rewrite.
///
/// The text goes in through the child's stdin and comes back on its stdout as one line
/// of JSON, so nothing a person pasted is ever written to a temporary file. The window
/// reimplements no part of the rewriting: the transforms, the coverage check and every
/// number under the text are reflip's, and this class launches it, follows where it has
/// got to, and renders what it printed.
@MainActor
final class Rewriter: ObservableObject {

    /// Live progress, observed only where it is drawn.
    let live = RunState()

    @Published private(set) var isRunning = false
    /// The last finished rewrite, receipt and all. Nil until the first one lands, which
    /// is the state the bottom strip has its own sentence for.
    @Published private(set) var receipt: Receipt?
    @Published var errorText: String?

    var text: String { receipt?.text ?? "" }

    /// How a run ended. All three are needed: a stop somebody asked for is not a
    /// failure, and reporting it as one is a button apologising for working.
    enum Outcome { case finished, failed, cancelled }

    /// Put a receipt in the window without running anything.
    ///
    /// Only `Shot.arrange` calls this, and only under `--sample`, to give the layout
    /// something to draw for the pictures in the README. It is the one door into this
    /// object that does not go through reflip, which is why it is three lines long and
    /// next to the ones that do.
    func show(_ receipt: Receipt) {
        self.receipt = receipt
    }

    private var process: Process?
    private var outBuffer = Data()
    private var reader = LineReader()
    private var lastPublish = Date.distantPast
    /// The sentence from an `{"event":"error"}` line, and the last line that was not
    /// JSON at all. Held off the published properties because nothing draws them while
    /// the run is going, and because the throttle below would drop the one line that
    /// says why a failure happened.
    private var trouble: String?
    private var lastPlain = ""
    private(set) var wasCancelled = false

    func rewrite(text: String, transform: Transform, stride: Int, model: String,
                 checkCoverage: Bool, onFinish: ((Outcome) -> Void)? = nil) {
        guard !isRunning else { return }
        guard !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return }
        // `-` is stdin. The alternative is a temporary file with somebody's draft in it,
        // left in /tmp for the next person with a disk utility.
        var arguments = ["rewrite", "-", "--transform", transform.rawValue,
                         "--json", "--progress"]
        if transform.takesStride { arguments += ["--stride", String(stride)] }
        if !model.isEmpty { arguments += ["--model", model] }
        if !checkCoverage { arguments.append("--no-coverage") }
        launch(arguments, feeding: text, onFinish: onFinish)
    }

    private func launch(_ arguments: [String], feeding input: String,
                        onFinish: ((Outcome) -> Void)?) {
        isRunning = true
        wasCancelled = false
        errorText = nil
        trouble = nil
        lastPlain = ""
        receipt = nil
        outBuffer = Data()
        reader = LineReader()
        lastPublish = .distantPast
        live.reset()

        let proc = Process()
        proc.executableURL = URL(fileURLWithPath: Cli.path)
        proc.arguments = arguments
        proc.environment = Cli.environment()

        let inPipe = Pipe(), outPipe = Pipe(), errPipe = Pipe()
        proc.standardInput = inPipe
        proc.standardOutput = outPipe
        proc.standardError = errPipe

        // Both pipes are drained, for two different reasons.
        //
        // stdout carries the receipt, one line of JSON at the end, and stderr carries
        // the progress. That is the reading half. The other half is survival: an unread
        // pipe stops at 64 KB and the child blocks writing into it for ever. The
        // rewritten text goes out through stdout, so 64 KB is not a theoretical amount
        // of text, it is about eleven thousand words.
        outPipe.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let chunk = handle.availableData
            guard !chunk.isEmpty else { return }
            Task { @MainActor in self?.outBuffer.append(chunk) }
        }
        errPipe.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let chunk = handle.availableData
            guard !chunk.isEmpty, let text = String(data: chunk, encoding: .utf8) else { return }
            Task { @MainActor in self?.ingest(text) }
        }

        proc.terminationHandler = { [weak self] finished in
            // Whatever arrived after the last callback. The receipt is the very last
            // thing printed, so without this the run that worked looked like the run
            // that said nothing.
            let tailOut = (try? outPipe.fileHandleForReading.readToEnd()) ?? nil
            let tailErr = (try? errPipe.fileHandleForReading.readToEnd()) ?? nil
            Task { @MainActor in
                outPipe.fileHandleForReading.readabilityHandler = nil
                errPipe.fileHandleForReading.readabilityHandler = nil
                if let tailOut { self?.outBuffer.append(tailOut) }
                if let tailErr, let text = String(data: tailErr, encoding: .utf8) {
                    self?.ingest(text)
                }
                self?.close(out: finished, onFinish: onFinish)
            }
        }

        do {
            try proc.run()
            process = proc
        } catch {
            isRunning = false
            errorText = "Cannot run \(Cli.path): \(error.localizedDescription)"
            onFinish?(.failed)
            return
        }

        // The text has to be written from another thread. A pipe holds 64 KB, and
        // anything longer blocks here until the child has read the first half, which it
        // cannot do while the main thread is stuck inside this function.
        let data = Data(input.utf8)
        DispatchQueue.global(qos: .userInitiated).async {
            let handle = inPipe.fileHandleForWriting
            try? handle.write(contentsOf: data)
            try? handle.close()
        }
    }

    func cancel() {
        guard isRunning else { return }
        wasCancelled = true
        process?.terminate()
        process = nil
        isRunning = false
        live.reset()
        errorText = nil
    }

    /// Kill the child before the app goes away. A terminated app leaves reflip running
    /// with a model resident and no window left to say what is using the machine.
    func terminateChild() {
        process?.terminate()
        process = nil
    }

    private func ingest(_ chunk: String) { absorb(reader.feed(chunk)) }

    /// What was left after the last newline. reflip's own last line always ends with
    /// one; a refusal printed by something it imports does not, and that line is the
    /// only place the reason is written.
    private func drain() { absorb(reader.flush()) }

    private func absorb(_ lines: [String]) {
        guard !lines.isEmpty else { return }
        var phase: String?
        var note: String?
        var progress: Double?

        for line in lines {
            guard let event = Event.from(line) else {
                // Not one of reflip's events: a warning from a library it imports, or
                // the plain sentence a refusal prints. Kept, because on a failure it is
                // usually the only thing that says why.
                lastPlain = line
                continue
            }
            if event.event == "error" {
                if let message = event.message, !message.isEmpty { trouble = message }
                continue
            }
            if let value = event.phase { phase = value }
            if let value = event.message { note = value }
            if let value = event.fraction { progress = value }
        }

        // A change of phase is worth a redraw at once. Everything else waits for the
        // next tick: a screen cannot show more than a few frames a second and reflip
        // reports a paragraph at a time, faster than that on short ones.
        let now = Date()
        let phaseChanged = phase != nil && phase != live.phase
        guard phaseChanged || now.timeIntervalSince(lastPublish) > 0.25 else { return }
        lastPublish = now
        if let phase { live.phase = phase }
        if let note { live.note = note }
        if let progress { live.progress = progress }
        live.lastLine = lastPlain
    }

    private func close(out finished: Process, onFinish: ((Outcome) -> Void)?) {
        // Stop, then start again straight away, and this handler belongs to the process
        // that was killed. Letting it run marked the new rewrite as failed and cleared
        // the receipt out from under it, and draining here would eat the first lines of
        // the rewrite that replaced it.
        guard process == nil || process === finished else { return }
        drain()
        isRunning = false
        process = nil
        live.progress = nil

        if wasCancelled {
            wasCancelled = false
            errorText = nil
            onFinish?(.cancelled)
            return
        }

        let body = Cli.lastLine(of: outBuffer)
        if finished.terminationStatus == 0, let body,
           let parsed = try? JSONDecoder().decode(Receipt.self, from: body) {
            receipt = parsed
            onFinish?(.finished)
            return
        }
        errorText = failure(status: finished.terminationStatus, body: body)
        onFinish?(.failed)
    }

    /// Why it stopped, in reflip's words wherever reflip supplied any. Exit code 1 is
    /// an expected refusal and always carries a sentence, on stdout as JSON or plain on
    /// stderr; only the last line here is this window's own.
    private func failure(status: Int32, body: Data?) -> String {
        if let body, let refusal = try? JSONDecoder().decode(Refusal.self, from: body),
           let sentence = refusal.sentence {
            return sentence
        }
        if let trouble, !trouble.isEmpty { return trouble }
        if !lastPlain.isEmpty { return lastPlain }
        if status == 130 { return "The rewrite was interrupted." }
        return "reflip stopped with code \(status) and said nothing."
    }
}
