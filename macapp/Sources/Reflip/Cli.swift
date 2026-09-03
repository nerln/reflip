import Foundation

/// Running the `reflip` command, which is the only way this window knows anything.
///
/// There is no library to link against and no daemon to talk to. reflip is a Python
/// package that drives a local model server, and everything worth saying about a text,
/// what a transform did to it and what it cost, is decided there. So the window runs
/// the command a person could have typed and renders the answer. Every explanation on
/// screen arrives from the command as a string, which is why this window cannot claim
/// a text is clean when reflip says it is not.
enum Cli {
    static let pathKey = "reflipPath"
    static let urlKey = "reflipServerUrl"
    static let modelKey = "reflipModel"

    /// Where Ollama listens when nobody has moved it. Kept here because the Settings
    /// pane offers to change it and has to show something when nobody has.
    static let defaultUrl = "http://localhost:11434"

    static var path: String {
        get { UserDefaults.standard.string(forKey: pathKey) ?? discovered }
        set {
            UserDefaults.standard.set(newValue.trimmingCharacters(in: .whitespaces),
                                      forKey: pathKey)
        }
    }

    /// Where the model server listens. Handed to the child in its environment rather
    /// than on the command line: the flag belongs to reflip's own parser, and a window
    /// that guesses the spelling of a flag turns a setting into "usage error, code 2".
    static var serverUrl: String {
        get { UserDefaults.standard.string(forKey: urlKey) ?? defaultUrl }
        set {
            UserDefaults.standard.set(newValue.trimmingCharacters(in: .whitespaces),
                                      forKey: urlKey)
        }
    }

    /// The model the person picked, or empty for whatever reflip would choose on its
    /// own. Empty rather than a name spelled out here: the recommended rewriter is a
    /// measured result that lives in the Python package and moves when the numbers do.
    static var model: String {
        get { UserDefaults.standard.string(forKey: modelKey) ?? "" }
        set {
            UserDefaults.standard.set(newValue.trimmingCharacters(in: .whitespaces),
                                      forKey: modelKey)
        }
    }

    static var isUsable: Bool { FileManager.default.isExecutableFile(atPath: path) }

    static let discovered: String = {
        discover(environment: ProcessInfo.processInfo.environment,
                 home: FileManager.default.homeDirectoryForCurrentUser.path,
                 beside: Bundle.main.bundleURL
                     .deletingLastPathComponent()
                     .deletingLastPathComponent()
                     .appendingPathComponent("bin/reflip").path,
                 isExecutable: { FileManager.default.isExecutableFile(atPath: $0) })
    }()

    /// Where reflip is, on a Mac where nobody has said.
    ///
    /// PATH is not enough. An application started from the Dock inherits a PATH with
    /// neither ~/.local/bin nor /opt/homebrew/bin on it, so the window found nothing
    /// while the same command worked in every terminal on the machine. The last
    /// candidate is a clone that was never installed, where the app sits in macapp/
    /// and the command sits in bin/ beside it.
    ///
    /// An explicit REFLIP_BIN wins whether or not it is runnable: somebody who set it
    /// is better served by "nothing runnable at the path you gave" than by the window
    /// quietly using a different reflip.
    static func discover(environment: [String: String], home: String, beside: String,
                         isExecutable: (String) -> Bool) -> String {
        if let given = environment["REFLIP_BIN"], !given.isEmpty { return given }
        var candidates: [String] = []
        if let raw = environment["PATH"] {
            candidates += raw.split(separator: ":").map { "\($0)/reflip" }
        }
        candidates += ["\(home)/.local/bin/reflip", "/opt/homebrew/bin/reflip",
                       "/usr/local/bin/reflip", "/usr/bin/reflip"]
        candidates.append(beside)
        return candidates.first(where: isExecutable) ?? "\(home)/.local/bin/reflip"
    }

    /// The environment every child gets.
    static func environment() -> [String: String] {
        var env = ProcessInfo.processInfo.environment
        // reflip shells out to `ollama`, and an app launched from the Finder has a PATH
        // with neither Homebrew nor ~/.local/bin on it. Without this the strip said
        // ollama was not installed on a machine where it was, and it said it only to
        // people who had not started the app from a terminal.
        let home = FileManager.default.homeDirectoryForCurrentUser.path
        var extra = ["\(home)/.local/bin", "/opt/homebrew/bin", "/usr/local/bin",
                     "/usr/bin", "/bin"]
        extra.insert(URL(fileURLWithPath: path).deletingLastPathComponent().path, at: 0)
        env["PATH"] = (extra + [env["PATH"] ?? ""]).joined(separator: ":")
        // Python buffers stdout when it is a pipe, which is exactly what it is here.
        // Without this the progress lines all arrived at once, at the end, which is
        // the one moment they are worth nothing.
        env["PYTHONUNBUFFERED"] = "1"
        let url = serverUrl
        if !url.isEmpty { env["REFLIP_BASE_URL"] = url }
        return env
    }

    struct Output {
        let status: Int32
        let out: Data
        let err: String
    }

    /// Run reflip once and wait for it. Never throws: a window that raises because a
    /// command line is missing is a window that cannot tell you the command line is
    /// missing.
    static func run(_ arguments: [String]) async -> Output {
        let tool = path
        let env = environment()
        return await Task.detached(priority: .userInitiated) { () -> Output in
            let proc = Process()
            proc.executableURL = URL(fileURLWithPath: tool)
            proc.arguments = arguments
            proc.environment = env
            let out = Pipe(), err = Pipe()
            proc.standardOutput = out
            proc.standardError = err
            // Nothing on stdin. A command that decides to read it would inherit the
            // window's, and then wait for a keystroke that cannot arrive.
            proc.standardInput = FileHandle.nullDevice
            do {
                try proc.run()
            } catch {
                return Output(status: 127, out: Data(),
                              err: "Could not run \(tool): \(error.localizedDescription)")
            }
            // Read before waiting. A status answer listing twenty models is small, but
            // a process whose pipe is full blocks for ever, and there is no size at
            // which waiting first becomes safe.
            let data = out.fileHandleForReading.readDataToEndOfFile()
            let problem = err.fileHandleForReading.readDataToEndOfFile()
            proc.waitUntilExit()
            return Output(status: proc.terminationStatus, out: data,
                          err: String(data: problem, encoding: .utf8) ?? "")
        }.value
    }

    /// The last line with anything on it, which is where the answer is.
    ///
    /// The contract is one line of JSON on stdout, and the libraries reflip imports
    /// print warnings above it. Decoding the whole buffer failed on the warning, and
    /// the window reported that reflip had answered with something it could not read
    /// while the answer sat on the line below.
    static func lastLine(of data: Data) -> Data? {
        guard let text = String(data: data, encoding: .utf8) else { return nil }
        guard let line = text.split(separator: "\n").last(where: {
            !$0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        }) else { return nil }
        return Data(line.trimmingCharacters(in: .whitespacesAndNewlines).utf8)
    }
}

/// Lines out of a pipe.
///
/// A pipe hands over bytes, not lines. Splitting each chunk as though it were whole cut
/// a line wherever the buffer boundary fell, and the half carrying `{"event":"progress"`
/// was dropped: a rewrite that takes a minute never ticked, and a download sat at zero
/// while it downloaded. Whatever comes after the last newline waits for the next chunk.
struct LineReader {
    private var residue = ""

    /// A single line longer than this is a program drawing a progress bar with no
    /// newline in it. Holding it for ever is worse than showing it late.
    private static let giveUp = 65_536

    mutating func feed(_ chunk: String) -> [String] {
        let combined = residue + chunk
        guard let lastBreak = combined.lastIndex(of: "\n") else {
            residue = combined
            guard residue.count > Self.giveUp else { return [] }
            let whole = residue
            residue = ""
            return Self.tidy(whole)
        }
        residue = String(combined[combined.index(after: lastBreak)...])
        return Self.tidy(String(combined[..<lastBreak]))
    }

    /// What is left when the child has gone. The reason a run stopped is usually on the
    /// last line, and a program that dies does not always end it with a newline.
    mutating func flush() -> [String] {
        let rest = residue
        residue = ""
        return Self.tidy(rest)
    }

    private static func tidy(_ text: String) -> [String] {
        text.split(separator: "\n", omittingEmptySubsequences: false)
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
    }
}
