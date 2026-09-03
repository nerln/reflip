import SwiftUI

/// The strip at the top: whether a rewrite could run at all.
///
/// It sits above the text rather than beside a button, because what decides whether
/// anything can happen is a property of the machine and not of the text. A coloured
/// dot, reflip's sentence about the server, the model, and the one thing worth pressing
/// about it. Every sentence here came out of `reflip server status --json`; the window
/// chooses which of them to show and nothing else.
struct ServerStrip: View {
    @ObservedObject var store: ServerStore
    @Binding var model: String
    let onStart: () -> Void
    let onStop: () -> Void
    let onDownload: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .top, spacing: 10) {
                Circle()
                    .fill(tint)
                    .frame(width: 9, height: 9)
                    .padding(.top, 5)

                VStack(alignment: .leading, spacing: 2) {
                    Text(sentence)
                        .font(.callout)
                        .foregroundStyle(isBroken ? Color.red : Color.primary)
                        .fixedSize(horizontal: false, vertical: true)
                    if let second {
                        Text(second)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }

                Spacer(minLength: 12)

                Picker("Model", selection: $model) {
                    ForEach(choices, id: \.self) { name in
                        Text(name).tag(name)
                    }
                }
                .labelsHidden()
                .frame(maxWidth: 240)
                .disabled(choices.isEmpty || store.isPulling)

                Button(buttonLabel) { press() }
                    .disabled(!canPress)
            }

            if store.isPulling {
                PullRow(pull: store.pull) { store.cancelDownload() }
            }

            // reflip's own words for why the machine is not what the free memory
            // suggests. A rewrite that refuses to start while the Mac looks half empty
            // is the moment somebody decides the tool is broken.
            ForEach(machineReasons, id: \.self) { reason in
                Label(reason, systemImage: "exclamationmark.triangle.fill")
                    .font(.caption)
                    .foregroundStyle(.orange)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
        .background(.regularMaterial)
        .overlay(alignment: .bottom) { Divider() }
    }

    // MARK: - what it says

    private var sentence: String {
        if let problem = store.problem { return problem }
        if let status = store.status { return status.sentence }
        return "Asking reflip about the model server."
    }

    /// The second line, when there is one to add. reflip writes both `reason` fields as
    /// whole sentences and either may be null; showing the same sentence twice because
    /// one repeats the other is worse than showing one.
    private var second: String? {
        if let note = store.note, note != sentence { return note }
        guard let status = store.status else { return nil }
        for candidate in [status.server.reason, status.reason] {
            if let candidate, !candidate.isEmpty, candidate != sentence { return candidate }
        }
        // Only when the machine was actually read. reflip reports zero on a platform it
        // cannot measure, and "0B free for work" reads as a machine with nothing left
        // rather than as a figure nobody took.
        guard status.ready, status.machine.freeForWork > 0 else { return nil }
        return "\(Format.bytes(status.machine.freeForWork)) free for work on this Mac."
    }

    private var machineReasons: [String] {
        store.status?.machine.reasons ?? []
    }

    /// reflip itself could not be run, so there is no state at all. Kept apart from a
    /// server that is down: the strip has to say something in both cases, and the two
    /// sentences send a person to different places. Without this the bar was empty and
    /// grey on the one machine where the window is useless, which is the machine most
    /// likely to be the one somebody is looking at.
    private var isBroken: Bool { store.status == nil && store.problem != nil }

    private var tint: Color {
        if isBroken { return .red }
        guard let status = store.status else { return .secondary }
        if !status.server.installed { return .red }
        if status.ready { return .green }
        return .orange
    }

    // MARK: - the one thing worth pressing

    /// What the button does next. Downloading comes before stopping because a server
    /// that is up without the model is a server that cannot do the only thing this
    /// window is for.
    private enum Move { case unknown, missingOllama, start, download, stop }

    private var move: Move {
        guard let status = store.status else { return .unknown }
        if !status.server.installed { return .missingOllama }
        if !status.server.running { return .start }
        if !chosen.isEmpty && !status.has(chosen) { return .download }
        return .stop
    }

    private var buttonLabel: String {
        switch move {
        case .download: return "Download the model"
        case .stop: return "Stop the server"
        case .unknown, .missingOllama, .start: return "Start the server"
        }
    }

    private var canPress: Bool {
        guard !store.isBusy, !store.isPulling else { return false }
        switch move {
        case .unknown, .missingOllama: return false
        case .start, .download, .stop: return true
        }
    }

    private func press() {
        switch move {
        case .start: onStart()
        case .stop: onStop()
        case .download: onDownload()
        case .unknown, .missingOllama: break
        }
    }

    // MARK: - the models

    private var chosen: String {
        model.isEmpty ? (store.status?.model ?? "") : model
    }

    /// What is on the disk, plus the model reflip would pick and the one the person
    /// picked, whether or not either has been downloaded. A picker offering only what
    /// is installed cannot be used to install anything.
    private var choices: [String] {
        var names = store.status?.server.models.map(\.name) ?? []
        for extra in [store.status?.model, model.isEmpty ? nil : model] {
            guard let extra, !extra.isEmpty else { continue }
            if !names.contains(extra) { names.append(extra) }
        }
        return names.sorted()
    }
}

/// The download, drawn where the model picker is, for as long as it takes.
///
/// Its own view because it observes the fast-moving object. Inside the strip it would
/// have redrawn the strip, and the strip is most of the window's chrome.
struct PullRow: View {
    @ObservedObject var pull: PullState
    let onStop: () -> Void

    var body: some View {
        HStack(spacing: 10) {
            if let fraction = pull.fraction {
                ProgressView(value: fraction)
                    .frame(width: 180)
                Text("\(Format.bytes(pull.completed)) of \(Format.bytes(pull.total))")
                    .font(.caption)
                    .monospacedDigit()
                    .foregroundStyle(.secondary)
            } else {
                ProgressView()
                    .controlSize(.small)
            }
            Text(pull.line)
                .font(.caption)
                .foregroundStyle(.secondary)
                .lineLimit(1)
            Spacer(minLength: 8)
            Button("Stop") { onStop() }
        }
    }
}
