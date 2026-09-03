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
    /// reflip's own sentence for why coverage is null: no tokenizer named, transformers
    /// not installed, or the tokenizer failed to load. Null when coverage was measured.
    /// The strip used to make up "coverage was not checked" for every one of those cases
    /// alike, which is exactly the kind of explanation this window is not supposed to
    /// write for itself.
    let coverageNote: String?
    let llmCalls: Int
    let promptTokens: Int
    let completionTokens: Int
    let seconds: Double

    var tokens: Int { promptTokens + completionTokens }

    enum CodingKeys: String, CodingKey {
        case transform, model, text, words, edits, coverage, seconds
        case editRatio = "edit_ratio"
        case coverageNote = "coverage_note"
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
        coverageNote = try box.decodeIfPresent(String.self, forKey: .coverageNote)
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

/// One transform reflip knows how to apply, named the way the command line names it.
///
/// This used to be a Swift `enum` with four fixed cases, compiled into the app. The
/// fifth transform, `hybrid`, was added to reflip and this window did not know it
/// existed until it was told in words: a tool whose list of transforms lives in the
/// binary needs a new build to learn about one the command line already knows, which is
/// the same mistake the model catalogue below exists to avoid. `reflip transforms` is
/// the list now, asked once when the window opens; the four sentences the README calls
/// out by name stay here as a lookup, because they are prose written for this window
/// and not something the command line prints, and anything reflip has that this lookup
/// does not falls back to its own name, title-cased, rather than disappearing from the
/// picker or showing raw command-line spelling.
enum TransformCatalogue {
    private static let labels: [String: String] = [
        "paraphrase": "Rewrite every paragraph (best result)",
        "infill": "Replace one word in every few (keeps more of the original)",
        "rules": "Word rules only, no model (partial)",
        "unicode": "Strip invisible characters only (does nothing to the watermark)",
    ]

    /// The sentence a person reads before pressing the button.
    static func label(for name: String) -> String {
        labels[name] ?? name.replacingOccurrences(of: "_", with: " ").capitalized
    }

    /// Whether the stride stepper does anything for this transform. reflip accepts
    /// `--stride` unconditionally, whether or not a transform reads it, so this decides
    /// only whether the stepper reads as live or as decoration; a name this window has
    /// never heard of defaults to "no", the same as `rules` and `unicode` today, because
    /// a control that looks live but quietly does nothing is worse than one that looks
    /// grey.
    static func takesStride(_ name: String) -> Bool {
        name == "infill" || name == "hybrid"
    }

    /// Whether a rewrite with this transform is expected to need the model server.
    /// Nothing downstream trusts this for correctness: reflip decides for itself and
    /// refuses with its own sentence when the server is not ready. It only shapes the
    /// hint this window shows before that refusal would happen.
    static func needsModel(_ name: String) -> Bool {
        name != "rules" && name != "unicode"
    }

    /// `reflip transforms`, one name per line. Falls back to the four this window has
    /// always offered if the command could not be asked at all, so a broken path to
    /// reflip empties the picker rather than the whole window: the strip above already
    /// says reflip could not be found, and the picker repeating that sentence adds
    /// nothing.
    /// `reflip transforms --json`, including the full path and sentence for any of a
    /// person's own transform files in `~/.reflip/transforms` that failed to load.
    /// Falls back to the four this window has always offered, with no load errors, if
    /// the command could not be asked at all or answered with something that would not
    /// decode: a broken path to reflip empties the picker rather than the whole window,
    /// and there is nothing to say about files this window was never told about.
    static func fetch() async -> (names: [String], loadErrors: [String]) {
        let result = await Cli.run(["transforms", "--json"])
        guard let body = Cli.lastLine(of: result.out),
              let parsed = try? JSONDecoder().decode(TransformsResponse.self, from: body),
              !parsed.transforms.isEmpty
        else {
            return (["paraphrase", "infill", "rules", "unicode"], [])
        }
        // The same sentence reflip's own plain-text mode prints for one of these
        // (`cli.py`'s `cmd_transforms`): the full path first, because a person's own
        // file living in their home directory is not named the way reflip's built-in
        // transforms are, and "rules did not load" would read as reflip's own transform
        // being broken rather than a typo in somebody's own script.
        let errors = parsed.localErrors.map { filename, why in
            "\(parsed.localDir)/\(filename) did not load. \(why)"
        }.sorted()
        return (parsed.transforms, errors)
    }
}

/// What `reflip transforms --json` answers.
struct TransformsResponse: Decodable, Equatable {
    let transforms: [String]
    let localDir: String
    /// File name to the sentence explaining why it did not load. Empty on a machine
    /// with no transforms of its own, or where every one of them loaded fine.
    let localErrors: [String: String]

    enum CodingKeys: String, CodingKey {
        case transforms
        case localDir = "local_dir"
        case localErrors = "local_errors"
    }
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

    /// A detector's z-score, one decimal place. Unlike `seconds`, this can be negative:
    /// unwatermarked text scores a little below zero, and rounding "-0.28" down to "-0"
    /// would read as broken math rather than as the good result it is.
    static func zScore(_ value: Double) -> String {
        String(format: "%.1f", value)
    }

    /// The catalogue's own download sizes arrive already in GB, unlike everything else
    /// in this window, which counts bytes. A second unit through `bytes(_:)` would ask
    /// it to convert a number that is not one.
    static func gigabytes(_ value: Double) -> String {
        String(format: "%.1f GB", value)
    }
}
