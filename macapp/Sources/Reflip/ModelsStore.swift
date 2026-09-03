import Foundation
import SwiftUI

/// What the Models window knows, and the three things it can do about it: download a
/// model, measure one, and read what is already on this Mac.
///
/// A window of its own on purpose, not a second view onto `ServerStore`. That store polls
/// the server every three seconds for the strip at the top, and its one download slot
/// belongs to the picker beside it; this window has its own list of rows, each of which
/// can start its own download or its own measurement, and sharing one `Process` reference
/// between two screens is how a download started from the strip would be reported to a
/// row that never asked for it. The two windows agree on which model is "in use" the same
/// way the Settings window and this one already agree on the path to reflip: through
/// `Cli.model`, not through a live reference passed between them.
@MainActor
final class ModelsStore: ObservableObject {

    // MARK: - what is on this Mac

    @Published private(set) var installed: [InstalledModel] = []
    /// reflip's own default, read from `server status`. "In use" is this unless somebody
    /// has chosen a different one, which is exactly how the main window works out the
    /// same answer.
    @Published private(set) var defaultModel = ""
    @Published private(set) var installedProblem: String?
    @Published private(set) var isLoadingInstalled = false

    var chosenModel: String {
        let picked = Cli.model
        return picked.isEmpty ? defaultModel : picked
    }

    func isInUse(_ name: String) -> Bool {
        guard !chosenModel.isEmpty else { return false }
        return ServerStatus.tagged(name) == ServerStatus.tagged(chosenModel)
    }

    func loadInstalled() async {
        guard !isLoadingInstalled else { return }
        isLoadingInstalled = true
        let result = await Cli.run(["server", "status", "--json"])
        isLoadingInstalled = false
        guard let body = Cli.lastLine(of: result.out),
              let status = try? JSONDecoder().decode(ServerStatus.self, from: body) else {
            installedProblem = Cli.isUsable
                ? "reflip could not be asked what is on this Mac."
                : "No reflip at \(Cli.path). Open Settings and point this at the command."
            return
        }
        installedProblem = nil
        installed = status.server.models
        defaultModel = status.model
    }

    // MARK: - the catalogue

    @Published private(set) var recommended: RecommendedModels?
    @Published private(set) var recommendedProblem: String?
    @Published private(set) var isLoadingRecommended = false

    func loadRecommended() async {
        guard !isLoadingRecommended else { return }
        isLoadingRecommended = true
        let result = await Cli.run(["models", "--recommended", "--json"])
        isLoadingRecommended = false
        guard let body = Cli.lastLine(of: result.out),
              let parsed = try? JSONDecoder().decode(RecommendedModels.self, from: body) else {
            recommendedProblem = Cli.isUsable
                ? "reflip could not be asked for the catalogue."
                : "No reflip at \(Cli.path). Open Settings and point this at the command."
            return
        }
        recommendedProblem = nil
        recommended = parsed
    }

    // MARK: - search

    @Published var query = ""
    @Published private(set) var search: SearchResults?
    @Published private(set) var searchProblem: String?
    @Published private(set) var isSearching = false

    func runSearch() async {
        let asked = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !asked.isEmpty, !isSearching else { return }
        isSearching = true
        searchProblem = nil
        let result = await Cli.run(["models", "--search", asked, "--json"])
        isSearching = false
        guard let body = Cli.lastLine(of: result.out),
              let parsed = try? JSONDecoder().decode(SearchResults.self, from: body) else {
            searchProblem = Cli.isUsable
                ? "reflip could not be asked to search Hugging Face."
                : "No reflip at \(Cli.path). Open Settings and point this at the command."
            return
        }
        search = parsed
        // The command itself already says why an empty search failed (offline, no
        // results): repeating that as a second sentence from this window would be the
        // one thing the house style exists to prevent.
    }

    // MARK: - download, one at a time across every row

    @Published private(set) var isPulling = false
    /// Which catalogue ref the running download is for, so the row it belongs to is the
    /// one that draws the bar. Every other row's Download button just stays enabled or
    /// disabled by `isPulling`; only this one also shows progress.
    @Published private(set) var pullingRef: String?
    let pull = PullState()

    private var puller: Process?
    private var pullReader = LineReader()
    private var pullLastPublish = Date.distantPast
    /// The sentence the `done` event carried, reflip's own words for whether the pull
    /// actually worked. Held apart from the published properties because nothing draws
    /// it while the download is running.
    private var pullDoneMessage: String?
    private var pullDoneOk: Bool?

    func download(_ ref: String) {
        guard !isPulling, !ref.isEmpty else { return }
        isPulling = true
        pullingRef = ref
        pull.reset()
        pullReader = LineReader()
        pullLastPublish = .distantPast
        pullDoneMessage = nil
        pullDoneOk = nil

        let proc = Process()
        proc.executableURL = URL(fileURLWithPath: Cli.path)
        proc.arguments = ["pull", ref, "--json"]
        proc.environment = Cli.environment()
        proc.standardInput = FileHandle.nullDevice
        let out = Pipe(), err = Pipe()
        proc.standardOutput = out
        proc.standardError = err

        out.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let chunk = handle.availableData
            guard !chunk.isEmpty, let text = String(data: chunk, encoding: .utf8) else { return }
            Task { @MainActor in self?.ingestPull(text) }
        }
        // Drained and dropped, the same as `ServerStore.download`: a pipe nobody reads
        // fills at 64 KB and stalls a multi-gigabyte download a quarter of the way in.
        err.fileHandleForReading.readabilityHandler = { handle in _ = handle.availableData }

        proc.terminationHandler = { [weak self] finished in
            let tail = (try? out.fileHandleForReading.readToEnd()) ?? nil
            Task { @MainActor in
                out.fileHandleForReading.readabilityHandler = nil
                err.fileHandleForReading.readabilityHandler = nil
                if let tail, let text = String(data: tail, encoding: .utf8) {
                    self?.ingestPull(text)
                }
                guard let self else { return }
                // Stale-handler guard: stop, then start another download straight away,
                // and this handler belongs to the process that was just replaced.
                // Letting it run marked the new download as failed and cleared the bar
                // out from under it.
                guard self.puller == nil || self.puller === finished else { return }
                self.drainPull()
                self.puller = nil
                self.isPulling = false
                self.pullingRef = nil
                self.pull.reset()
                // reflip's own sentence from the `done` event wherever there is one;
                // only when the process ended without ever printing one does this
                // window reach for its own last resort, the same ladder
                // `ServerStore.failure` climbs for the strip above.
                if self.pullDoneOk == false {
                    self.installedProblem = self.pullDoneMessage
                                          ?? "The download failed and reflip said nothing "
                                          + "about why."
                } else if finished.terminationStatus != 0 {
                    self.installedProblem = self.pullDoneMessage
                                          ?? "The download stopped with code "
                                          + "\(finished.terminationStatus)."
                }
                Task { await self.loadInstalled() }
            }
        }

        do {
            try proc.run()
            puller = proc
        } catch {
            isPulling = false
            pullingRef = nil
            installedProblem = "Cannot run \(Cli.path): \(error.localizedDescription)"
        }
    }

    func cancelDownload() {
        guard isPulling else { return }
        puller?.terminate()
        puller = nil
        isPulling = false
        pullingRef = nil
        pull.reset()
    }

    private func ingestPull(_ chunk: String) { absorbPull(pullReader.feed(chunk)) }
    private func drainPull() { absorbPull(pullReader.flush()) }

    private func absorbPull(_ lines: [String]) {
        guard !lines.isEmpty else { return }
        var line: String?
        var completed: Int?
        var total: Int?
        for text in lines {
            guard let event = Event.from(text) else { continue }
            if event.event == "done" {
                if let message = event.message, !message.isEmpty { pullDoneMessage = message }
                pullDoneOk = event.ok
                continue
            }
            if let stage = event.status { line = stage }
            if let value = event.completed { completed = value }
            if let value = event.total { total = value }
        }
        let now = Date()
        let stageChanged = line != nil && line != pull.line
        guard stageChanged || now.timeIntervalSince(pullLastPublish) > 0.25 else { return }
        pullLastPublish = now
        if let line { pull.line = line }
        if let completed { pull.completed = completed }
        if let total { pull.total = total }
    }

    // MARK: - measure, one at a time across every row

    @Published private(set) var isMeasuring = false
    @Published private(set) var measuringRef: String?
    /// Live phase and fraction while a measurement runs, the same small object
    /// `RunProgress` already knows how to draw for a rewrite.
    let measureLive = RunState()
    /// The last measurement for each ref this window has asked about, kept after the
    /// process exits so a row still shows its verdict once another row starts measuring.
    @Published private(set) var measurements: [String: MeasureResult] = [:]

    private var measureProc: Process?
    private var measureReader = LineReader()
    private var measureOutBuffer = Data()
    private var measureLastPublish = Date.distantPast
    private var measureTrouble: String?
    private var measureLastPlain = ""
    private var measureWasCancelled = false

    /// No `--samples` on this argument list: reflip's own default (3, at the time of
    /// writing) applies, the same as it would for anybody who typed the command without
    /// naming one. This window offers no stepper for that count, so choosing a number
    /// here instead of leaving the flag off would be this window deciding something on
    /// a person's behalf that they never asked it to decide.
    func measure(_ ref: String) {
        guard !isMeasuring, !ref.isEmpty else { return }
        isMeasuring = true
        measuringRef = ref
        measureWasCancelled = false
        measureTrouble = nil
        measureLastPlain = ""
        measureOutBuffer = Data()
        measureReader = LineReader()
        measureLastPublish = .distantPast
        measureLive.reset()

        let proc = Process()
        proc.executableURL = URL(fileURLWithPath: Cli.path)
        proc.arguments = ["models", "--measure", ref, "--json", "--progress"]
        proc.environment = Cli.environment()
        proc.standardInput = FileHandle.nullDevice

        let out = Pipe(), err = Pipe()
        proc.standardOutput = out
        proc.standardError = err

        // Both drained, the same reasoning as `Rewriter.launch`: stdout carries the one
        // JSON result at the end and stderr carries progress, and an unread pipe stops
        // the child cold at 64 KB whichever stream fills first.
        out.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let chunk = handle.availableData
            guard !chunk.isEmpty else { return }
            Task { @MainActor in self?.measureOutBuffer.append(chunk) }
        }
        err.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let chunk = handle.availableData
            guard !chunk.isEmpty, let text = String(data: chunk, encoding: .utf8) else { return }
            Task { @MainActor in self?.ingestMeasure(text) }
        }

        proc.terminationHandler = { [weak self] finished in
            let tailOut = (try? out.fileHandleForReading.readToEnd()) ?? nil
            let tailErr = (try? err.fileHandleForReading.readToEnd()) ?? nil
            Task { @MainActor in
                out.fileHandleForReading.readabilityHandler = nil
                err.fileHandleForReading.readabilityHandler = nil
                if let tailOut { self?.measureOutBuffer.append(tailOut) }
                if let tailErr, let text = String(data: tailErr, encoding: .utf8) {
                    self?.ingestMeasure(text)
                }
                self?.closeMeasure(out: finished, ref: ref)
            }
        }

        do {
            try proc.run()
            measureProc = proc
        } catch {
            isMeasuring = false
            measuringRef = nil
            measurements[ref] = .launchFailure(
                model: ref, reason: "Cannot run \(Cli.path): \(error.localizedDescription)")
        }
    }

    func cancelMeasure() {
        guard isMeasuring else { return }
        measureWasCancelled = true
        measureProc?.terminate()
        measureProc = nil
        isMeasuring = false
        measuringRef = nil
        measureLive.reset()
    }

    /// Kill both children before the app goes away. A download or a measurement left
    /// running holds a socket, and a measurement spends real model calls nobody asked
    /// for once the window that started it is gone.
    func terminateChildren() {
        puller?.terminate()
        puller = nil
        measureProc?.terminate()
        measureProc = nil
    }

    private func ingestMeasure(_ chunk: String) { absorbMeasure(measureReader.feed(chunk)) }
    private func drainMeasure() { absorbMeasure(measureReader.flush()) }

    private func absorbMeasure(_ lines: [String]) {
        guard !lines.isEmpty else { return }
        var phase: String?
        var note: String?
        var progress: Double?
        for line in lines {
            guard let event = Event.from(line) else {
                measureLastPlain = line
                continue
            }
            if event.event == "error" {
                if let message = event.message, !message.isEmpty { measureTrouble = message }
                continue
            }
            if let value = event.phase { phase = value }
            if let value = event.message { note = value }
            if let value = event.fraction { progress = value }
        }
        let now = Date()
        let phaseChanged = phase != nil && phase != measureLive.phase
        guard phaseChanged || now.timeIntervalSince(measureLastPublish) > 0.25 else { return }
        measureLastPublish = now
        if let phase { measureLive.phase = phase }
        if let note { measureLive.note = note }
        if let progress { measureLive.progress = progress }
        measureLive.lastLine = measureLastPlain
    }

    private func closeMeasure(out finished: Process, ref: String) {
        // Stale-handler guard, the same shape as `Rewriter.close`: a cancel followed by
        // a fresh measurement means this handler belongs to the process that was just
        // replaced, and letting it run would overwrite the new one's row with the old
        // one's outcome.
        guard measureProc == nil || measureProc === finished else { return }
        drainMeasure()
        isMeasuring = false
        measureProc = nil
        measuringRef = nil
        measureLive.progress = nil

        if measureWasCancelled {
            measureWasCancelled = false
            return
        }

        // Both a real measurement and an expected refusal print the same document
        // shape to stdout, whatever the exit code, so both are read the same way here.
        let body = Cli.lastLine(of: measureOutBuffer)
        if let body, let parsed = try? JSONDecoder().decode(MeasureResult.self, from: body) {
            measurements[ref] = parsed
            return
        }
        measurements[ref] = .launchFailure(model: ref, reason: measureFailureReason(
            status: finished.terminationStatus, body: body))
    }

    /// Why it stopped, in reflip's words wherever reflip supplied any. The same ladder
    /// `Rewriter.failure` climbs: an event on stderr, the last plain line, the interrupt
    /// code, and only then this window's own last resort.
    private func measureFailureReason(status: Int32, body: Data?) -> String {
        if let trouble = measureTrouble, !trouble.isEmpty { return trouble }
        if !measureLastPlain.isEmpty { return measureLastPlain }
        if status == 130 { return "The measurement was interrupted." }
        return "reflip stopped with code \(status) and said nothing."
    }
}
