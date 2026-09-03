import Foundation

// MARK: - what `reflip server status --json` answers

/// The model server as reflip describes it.
///
/// Nothing in this file decides anything. Whether the server is up, whether it is one
/// reflip started, and what a person should be told about either, is worked out in
/// Python and arrives here as a sentence. A second copy of that reasoning in Swift
/// would be a second answer, and the two would disagree on the day it mattered.
struct ServerStatus: Decodable, Equatable {
    /// True when a rewrite would run right now.
    let ready: Bool
    /// Null, or the whole sentence saying why not.
    let reason: String?
    /// The sentence for the strip, when reflip supplies one.
    let message: String?
    /// The model reflip would use if nobody chose one.
    let model: String
    let server: ServerInfo
    let machine: Machine

    /// What the strip says.
    ///
    /// reflip's own words wherever there are any. This was `message`, required, until a
    /// build of the command line that did not print that field turned a server that was
    /// up, with the model on the disk, into "reflip exited with code 0 and said nothing":
    /// one absent string blanked the whole strip and reported a fault that did not exist.
    /// The last line is this window's own, and only for the case where nothing at all
    /// came back to render.
    var sentence: String {
        for candidate in [message, reason, server.reason] {
            if let candidate, !candidate.isEmpty { return candidate }
        }
        return ready ? "The model server is up at \(server.url)."
                     : "The model server is not running."
    }

    /// Whether a model is on the disk already.
    ///
    /// Ollama writes a tag on every name and prints the long form, so a person who
    /// typed `llama3` and a server that lists `llama3:latest` mean the same file.
    /// Comparing the strings as they arrive said "not downloaded" about a model that
    /// was there, and offered to download it a second time.
    func has(_ name: String) -> Bool {
        let wanted = Self.tagged(name)
        return server.models.contains { Self.tagged($0.name) == wanted }
    }

    static func tagged(_ name: String) -> String {
        name.contains(":") ? name : name + ":latest"
    }
}

struct ServerInfo: Decodable, Equatable {
    let url: String
    let installed: Bool
    let running: Bool
    /// True when the running server is one reflip started. What to do about a server
    /// somebody else started is `reflip server stop`'s decision and not this window's;
    /// the button runs the command either way and shows the sentence that comes back.
    let ours: Bool
    let version: String?
    let reason: String?
    let models: [InstalledModel]
    /// The models the server is holding in memory right now.
    let loaded: [String]

    // Written out rather than synthesised: the initialiser below suppresses the one
    // the compiler would have made, and the errors it produces name every field except
    // the missing enum.
    enum CodingKeys: String, CodingKey {
        case url, installed, running, ours, version, reason, models, loaded
    }

    // Ollama missing altogether is the case this window most has to survive, and it is
    // the one where the two lists have nothing to say. Decoding them as required turned
    // "ollama is not installed" into "the window could not read the answer", which is
    // the least helpful of the two sentences.
    init(from decoder: Decoder) throws {
        let box = try decoder.container(keyedBy: CodingKeys.self)
        url = try box.decodeIfPresent(String.self, forKey: .url) ?? Cli.defaultUrl
        installed = try box.decodeIfPresent(Bool.self, forKey: .installed) ?? false
        running = try box.decodeIfPresent(Bool.self, forKey: .running) ?? false
        ours = try box.decodeIfPresent(Bool.self, forKey: .ours) ?? false
        version = try box.decodeIfPresent(String.self, forKey: .version)
        reason = try box.decodeIfPresent(String.self, forKey: .reason)
        models = try box.decodeIfPresent([InstalledModel].self, forKey: .models) ?? []
        loaded = try box.decodeIfPresent([String].self, forKey: .loaded) ?? []
    }
}

struct InstalledModel: Decodable, Equatable, Identifiable, Hashable {
    let name: String
    let size: Int
    let family: String?

    var id: String { name }
}

/// What the machine can spare, in reflip's terms.
///
/// A 4B model under Ollama needs about 2.5GB resident, and this laptop has 16GB with
/// Xcode in it. reflip works that out and says so; the strip repeats it.
struct Machine: Decodable, Equatable {
    let total: Int
    let freeForWork: Int
    let pressure: Int
    let swapUsed: Int
    let cores: Int
    let workers: Int
    /// reflip's own sentences for why the answer is not what the free memory suggests.
    /// Empty on a calm machine.
    let reasons: [String]

    enum CodingKeys: String, CodingKey {
        case total, pressure, cores, workers, reasons
        case freeForWork = "free_for_work"
        case swapUsed = "swap_used"
    }

    init(from decoder: Decoder) throws {
        let box = try decoder.container(keyedBy: CodingKeys.self)
        total = try box.decodeIfPresent(Int.self, forKey: .total) ?? 0
        freeForWork = try box.decodeIfPresent(Int.self, forKey: .freeForWork) ?? 0
        pressure = try box.decodeIfPresent(Int.self, forKey: .pressure) ?? 1
        swapUsed = try box.decodeIfPresent(Int.self, forKey: .swapUsed) ?? 0
        cores = try box.decodeIfPresent(Int.self, forKey: .cores) ?? 0
        workers = try box.decodeIfPresent(Int.self, forKey: .workers) ?? 1
        reasons = try box.decodeIfPresent([String].self, forKey: .reasons) ?? []
    }
}

// MARK: - what `reflip rewrite --json` answers

/// The rewritten text and what it cost.
///
/// The measurement is the product: forty other tools rewrite text, and what this one
/// adds is the four numbers underneath. They are read here exactly as reflip printed
/// them and are never recomputed from the text on screen.
struct Receipt: Decodable, Equatable {
    let transform: String
    /// Null for the two transforms that never call a model.
    let model: String?
    let text: String
    let words: Int
    let edits: Int
    let editRatio: Double
    /// Null when the coverage was not measured, which is not the same as zero and must
    /// never be drawn as zero: zero means the detector sees every position it saw
    /// before, and that is the one result worth shouting about.
    let coverage: Double?
    let llmCalls: Int
    let promptTokens: Int
    let completionTokens: Int
    let seconds: Double

    var tokens: Int { promptTokens + completionTokens }

    enum CodingKeys: String, CodingKey {
        case transform, model, text, words, edits, coverage, seconds
        case editRatio = "edit_ratio"
        case llmCalls = "llm_calls"
        case promptTokens = "prompt_tokens"
        case completionTokens = "completion_tokens"
    }

    // The counters are absent, not zero, for `rules` and `unicode`: those transforms
    // never open a socket, so there is nothing for them to report. Requiring the fields
    // made the two cheapest transforms the two that failed to decode.
    init(from decoder: Decoder) throws {
        let box = try decoder.container(keyedBy: CodingKeys.self)
        transform = try box.decodeIfPresent(String.self, forKey: .transform) ?? ""
        model = try box.decodeIfPresent(String.self, forKey: .model)
        text = try box.decode(String.self, forKey: .text)
        words = try box.decodeIfPresent(Int.self, forKey: .words) ?? 0
        edits = try box.decodeIfPresent(Int.self, forKey: .edits) ?? 0
        editRatio = try box.decodeIfPresent(Double.self, forKey: .editRatio) ?? 0
        coverage = try box.decodeIfPresent(Double.self, forKey: .coverage)
        llmCalls = try box.decodeIfPresent(Int.self, forKey: .llmCalls) ?? 0
        promptTokens = try box.decodeIfPresent(Int.self, forKey: .promptTokens) ?? 0
        completionTokens = try box.decodeIfPresent(Int.self, forKey: .completionTokens) ?? 0
        seconds = try box.decodeIfPresent(Double.self, forKey: .seconds) ?? 0
    }
}

/// An expected refusal: exit code 1, with the sentence on stdout as JSON.
///
/// The alert used to say "exit code 1" and drop the sentence, which turned "no model
/// server is running" into a number.
struct Refusal: Decodable {
    let reason: String?
    let message: String?

    var sentence: String? {
        for candidate in [reason, message] {
            if let candidate, !candidate.isEmpty { return candidate }
        }
        return nil
    }
}

/// One line of the JSON Lines a running command writes.
///
/// Progress and download share a decoder because the two differ only in which fields
/// are filled, and a second struct meant a second place to forget a null.
struct Event: Decodable {
    let event: String
    let phase: String?
    let done: Int?
    let total: Int?
    let message: String?
    let status: String?
    let completed: Int?
    let ok: Bool?

    /// Nil for anything that is not one of reflip's events, which on stderr is most of
    /// it: warnings from libraries reflip imports, and the plain sentence a refusal
    /// prints. Checking the first character keeps the decoder off every such line.
    static func from(_ line: String) -> Event? {
        guard line.hasPrefix("{") else { return nil }
        return try? JSONDecoder().decode(Event.self, from: Data(line.utf8))
    }

    var fraction: Double? {
        guard let total, total > 0, let done else { return nil }
        return min(max(Double(done) / Double(total), 0), 1)
    }
}

// MARK: - what a person can ask for

/// The four transforms, in the order the README puts them: the one that works, the one
/// that keeps more of the original, the one that gets part of the way with no model,
/// and the one that does nothing at all to the watermark.
///
/// That last one is here on purpose. It is what most of the "remover" sites do, and a
/// person who came looking for it should find it, try it, and read the receipt.
enum Transform: String, CaseIterable, Identifiable {
    case paraphrase, infill, rules, unicode

    var id: String { rawValue }

    var label: String {
        switch self {
        case .paraphrase: return "Rewrite every paragraph (best result)"
        case .infill: return "Replace one word in every few (keeps more of the original)"
        case .rules: return "Word rules only, no model (partial)"
        case .unicode: return "Strip invisible characters only (does nothing to the watermark)"
        }
    }

    /// Only the slot filler has a stride to set. The stepper stays visible for the
    /// others and goes grey, because hiding it moved the button out from under the
    /// pointer every time the transform changed.
    var takesStride: Bool { self == .infill }

    /// Whether this transform needs the model server at all.
    var needsModel: Bool { self == .paraphrase || self == .infill }
}

// MARK: - the same numbers the terminal prints

enum Format {
    /// Sizes in powers of two with one decimal, the way reflip prints them. A window
    /// that rounded differently would have somebody comparing two screens and finding
    /// two numbers for one thing.
    static func bytes(_ n: Int) -> String {
        var value = Double(n)
        for unit in ["B", "KB", "MB", "GB", "TB"] {
            if abs(value) < 1024 || unit == "TB" {
                return unit == "B" ? "\(Int(value))B"
                                   : String(format: "%.1f%@", value, unit)
            }
            value /= 1024
        }
        return String(format: "%.1fTB", value)
    }

    /// A share, as whole percent. The receipt has room for two digits and the third
    /// would be a lie about the precision of a measurement on one text.
    static func percent(_ share: Double) -> String {
        "\(Int((share * 100).rounded()))%"
    }

    static func seconds(_ value: Double) -> String {
        value < 100 ? String(format: "%.1f", value) : "\(Int(value.rounded()))"
    }

    static func count(_ n: Int) -> String {
        n.formatted(.number.grouping(.automatic))
    }
}
