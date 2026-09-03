import Foundation
import SwiftUI

/// The part of a download that changes several times a second.
///
/// Kept apart from the store on purpose. Ollama reports a byte count many times a
/// second, and when these lived on the store every one of those reports rebuilt the
/// whole window: both text editors, the picker and the receipt, for the length of a
/// 2.5GB download. Only the row that draws the bar observes this one.
@MainActor
final class PullState: ObservableObject {
    /// The server's own words for the stage it is in.
    @Published var line = ""
    @Published var completed = 0
    @Published var total = 0

    /// Nil while the total is unknown, which is most of the first second. A bar drawn
    /// from a zero total sits at the far left and reads as a download that is stuck.
    var fraction: Double? {
        guard total > 0 else { return nil }
        return min(max(Double(completed) / Double(total), 0), 1)
    }

    func reset() {
        line = ""
        completed = 0
        total = 0
    }
}

/// What the strip at the top knows, and the three things it can do about it.
///
/// Polling rather than watching anything: somebody else can start Ollama from a
/// terminal, stop it, or have the model unloaded under them by another program, and
/// none of that comes with a notification. Three seconds is slower than anybody can
/// act and cheap enough that the asking never shows up in the answer.
@MainActor
final class ServerStore: ObservableObject {
    @Published private(set) var status: ServerStatus?
    /// Set when reflip could not be asked at all. Kept apart from a server that is
    /// down: the two look alike in one line and mean opposite things.
    @Published private(set) var problem: String?
    @Published private(set) var isBusy = false
    @Published private(set) var isPulling = false
    /// What the last start, stop or download printed, in reflip's words.
    @Published var note: String?

    let pull = PullState()

    private var reading = false
    private var puller: Process?
    private var reader = LineReader()
    private var lastPublish = Date.distantPast

    // MARK: - reading

    func reload() {
        guard !reading else { return }
        reading = true
        Task {
            let result = await Cli.run(["server", "status", "--json"])
            reading = false
            absorb(result)
        }
    }

    /// Decode whatever came back, whatever the exit code.
    ///
    /// A server that is down is not an error: reflip still prints the whole document,
    /// with `ready` false and the sentence saying why. Treating a non-zero exit as a
    /// failure threw that sentence away and replaced it with the exit code.
    private func absorb(_ result: Cli.Output) {
        if let body = Cli.lastLine(of: result.out),
           let fresh = try? JSONDecoder().decode(ServerStatus.self, from: body) {
            problem = nil
            if fresh != status { status = fresh }
            return
        }
        problem = failure(result)
    }

    private func failure(_ result: Cli.Output) -> String {
        if !Cli.isUsable {
            return "No reflip at \(Cli.path). Open Settings and point this at the command."
        }
        let said = result.err.trimmingCharacters(in: .whitespacesAndNewlines)
        if let last = said.split(separator: "\n").last, !last.isEmpty { return String(last) }
        return "reflip exited with code \(result.status) and said nothing."
    }

    // MARK: - the three things a person can press

    func start() async { await act(["server", "start", "--json"]) }

    func stop() async { await act(["server", "stop", "--json"]) }

    private func act(_ arguments: [String]) async {
        guard !isBusy else { return }
        isBusy = true
        note = nil
        let result = await Cli.run(arguments)
        isBusy = false
        absorb(result)
        // Starting and stopping answer with the same document plus a sentence about
        // what just happened. That sentence is the only report a person gets that the
        // button did anything, and the next poll three seconds later overwrites it.
        note = status?.sentence
    }

    /// Download a model, following the byte count as it goes.
    func download(_ model: String) {
        guard !isPulling, !model.isEmpty else { return }
        isPulling = true
        note = nil
        problem = nil
        pull.reset()
        reader = LineReader()
        lastPublish = .distantPast

        let proc = Process()
        proc.executableURL = URL(fileURLWithPath: Cli.path)
        proc.arguments = ["pull", model, "--json"]
        proc.environment = Cli.environment()
        proc.standardInput = FileHandle.nullDevice
        let out = Pipe(), err = Pipe()
        proc.standardOutput = out
        proc.standardError = err

        out.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let chunk = handle.availableData
            guard !chunk.isEmpty, let text = String(data: chunk, encoding: .utf8) else { return }
            Task { @MainActor in self?.ingest(text) }
        }
        // Drained and dropped. Nothing on stderr is worth showing during a download,
        // and a pipe nobody reads fills at 64 KB and stops the download dead a quarter
        // of the way through a 2.5GB model.
        err.fileHandleForReading.readabilityHandler = { handle in _ = handle.availableData }

        proc.terminationHandler = { [weak self] finished in
            let tail = (try? out.fileHandleForReading.readToEnd()) ?? nil
            Task { @MainActor in
                out.fileHandleForReading.readabilityHandler = nil
                err.fileHandleForReading.readabilityHandler = nil
                if let tail, let text = String(data: tail, encoding: .utf8) {
                    self?.ingest(text)
                }
                guard let self else { return }
                // Stop, then start another download straight away, and this handler
                // belongs to the process that was killed. Letting it run marked the new
                // download as failed and cleared the bar out from under it, and draining
                // here would eat the first lines of the download that replaced it.
                guard self.puller == nil || self.puller === finished else { return }
                self.drain()
                self.puller = nil
                self.isPulling = false
                self.pull.reset()
                if finished.terminationStatus != 0 && self.note == nil {
                    self.problem = "The download stopped with code "
                                 + "\(finished.terminationStatus)."
                }
                self.reload()
            }
        }

        do {
            try proc.run()
            puller = proc
        } catch {
            isPulling = false
            problem = "Cannot run \(Cli.path): \(error.localizedDescription)"
        }
    }

    func cancelDownload() {
        guard isPulling else { return }
        puller?.terminate()
        puller = nil
        isPulling = false
        pull.reset()
        reload()
    }

    /// Kill the child before the app goes away. A download left behind carries on
    /// pulling gigabytes with no window left to say what is using the connection.
    func terminateChild() {
        puller?.terminate()
        puller = nil
    }

    private func ingest(_ chunk: String) { absorb(reader.feed(chunk)) }

    /// What was left after the last newline. The `done` event is the last thing a
    /// download prints and it carries the only sentence saying whether it worked.
    private func drain() { absorb(reader.flush()) }

    private func absorb(_ lines: [String]) {
        guard !lines.isEmpty else { return }
        var line: String?
        var completed: Int?
        var total: Int?

        for text in lines {
            guard let event = Event.from(text) else { continue }
            if event.event == "done" {
                if let message = event.message, !message.isEmpty { note = message }
                if event.ok == false { problem = event.message }
                continue
            }
            if let stage = event.status { line = stage }
            if let value = event.completed { completed = value }
            if let value = event.total { total = value }
        }

        // A new stage is worth a redraw at once. Everything else waits for the next
        // tick: Ollama reports the byte count faster than a screen can draw it, and
        // the window went sticky for the length of the download.
        let now = Date()
        let stageChanged = line != nil && line != pull.line
        guard stageChanged || now.timeIntervalSince(lastPublish) > 0.25 else { return }
        lastPublish = now
        if let line { pull.line = line }
        if let completed { pull.completed = completed }
        if let total { pull.total = total }
    }
}
