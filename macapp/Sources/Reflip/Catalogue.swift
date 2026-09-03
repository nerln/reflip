import Foundation

/// What `reflip models` answers in its three modes.
///
/// Nothing worth saying about a model is decided here. The catalogue's two sentences per
/// entry, whether a search result must be refused, and the verdict after a measurement
/// are all reflip's words, read exactly as printed. The one rule this file follows is the
/// same one `Receipt` follows: a figure that was not measured stays absent rather than
/// becoming a zero, because a zero here would be a claim nobody checked.

// MARK: - what `reflip models --recommended --json` answers

/// One entry in the catalogue: a model worth trying, with reflip's own sentences about
/// it.
///
/// This struct is not the list of models this window knows about. It is the shape of one
/// row in whatever list `reflip models --recommended` prints, which is the whole point:
/// the catalogue lives in the Python package, moves on its own schedule, and a build of
/// this window from last month already reads a catalogue entry it had never seen before
/// without being told what one looks like in advance, because the shape does not change,
/// only the rows do.
struct CatalogueModel: Decodable, Equatable, Identifiable {
    let ref: String
    let params: String
    let sizeGB: Double
    let goodAt: String
    let watchOut: String
    let languages: String
    /// What a real measurement on some machine said, in a sentence, or null for a model
    /// nobody has measured yet. Never a number on its own: a bare z-score with no context
    /// is not something a first-time reader can judge.
    let measured: String?
    /// True disqualifies rather than ranks: a model that watermarks its own output is
    /// never actually offered by the catalogue today, but this window does not assume
    /// that stays true and checks the field anyway.
    let watermarks: Bool
    let source: String
    let tags: [String]
    let installed: Bool

    var id: String { ref }

    enum CodingKeys: String, CodingKey {
        case ref, params, languages, measured, watermarks, source, tags, installed
        case sizeGB = "size_gb"
        case goodAt = "good_at"
        case watchOut = "watch_out"
    }
}

/// The catalogue plus what this Mac already has.
struct RecommendedModels: Decodable, Equatable {
    let recommended: [CatalogueModel]
    let defaultModel: String
    let installed: [String]
    /// Why the server itself could not be read, when there is a reason. Not shown as an
    /// error on its own: the catalogue is still worth showing even when the server is
    /// down, which is exactly when somebody most needs to pick a model to download.
    let serverReason: String?

    enum CodingKeys: String, CodingKey {
        case recommended, installed
        case defaultModel = "default"
        case serverReason = "server_reason"
    }

    // Defensive the way `ServerInfo` is, for the same reason: a future reflip that
    // drops or renames a field here should show an empty section rather than fail to
    // decode the whole window.
    init(from decoder: Decoder) throws {
        let box = try decoder.container(keyedBy: CodingKeys.self)
        recommended = try box.decodeIfPresent([CatalogueModel].self, forKey: .recommended) ?? []
        defaultModel = try box.decodeIfPresent(String.self, forKey: .defaultModel) ?? ""
        installed = try box.decodeIfPresent([String].self, forKey: .installed) ?? []
        serverReason = try box.decodeIfPresent(String.self, forKey: .serverReason)
    }
}

// MARK: - what `reflip models --search QUERY --json` answers

struct SearchResult: Decodable, Equatable, Identifiable {
    let ref: String
    let repo: String
    let downloads: Int
    let likes: Int
    let gated: Bool
    let page: String
    /// A sentence, when this model must never be used as the rewriter because it
    /// watermarks its own output, or null. A result carrying one is shown with no
    /// Download button at all: offering the button and refusing the click is a worse
    /// answer than not offering it.
    let refused: String?

    var id: String { ref }
}

struct SearchResults: Decodable, Equatable {
    let query: String
    let results: [SearchResult]
    /// reflip's own caution about the results, when it has one: that these are search
    /// results and not recommendations, or that Hugging Face could not be reached.
    let note: String?

    enum CodingKeys: String, CodingKey {
        case query, results, note
    }

    init(from decoder: Decoder) throws {
        let box = try decoder.container(keyedBy: CodingKeys.self)
        query = try box.decodeIfPresent(String.self, forKey: .query) ?? ""
        results = try box.decodeIfPresent([SearchResult].self, forKey: .results) ?? []
        note = try box.decodeIfPresent(String.self, forKey: .note)
    }
}

// MARK: - what `reflip models --measure MODEL --json` answers

/// Two shapes share one document. A refusal, because the model watermarks its own
/// output or because there is no benchmark corpus on this machine, carries only `ok`,
/// `model` and `reason`; a real measurement carries every figure below and no `reason`.
/// Every numeric field stays optional rather than defaulting to zero for the same
/// reason `Receipt.coverage` does: a zero here is itself a result worth reading, not a
/// stand-in for "this was not decoded".
struct MeasureResult: Decodable, Equatable {
    let ok: Bool
    let model: String
    let reason: String?
    let samples: Int?
    let errors: Int?
    let zBefore: Double?
    let zAfter: Double?
    let coverage: Double?
    let editRatio: Double?
    let seconds: Double?
    let tokensPer1kWords: Double?
    let coverageNote: String?
    let verdict: String?

    enum CodingKeys: String, CodingKey {
        case ok, model, reason, samples, errors, coverage, seconds, verdict
        case zBefore = "z_before"
        case zAfter = "z_after"
        case editRatio = "edit_ratio"
        case tokensPer1kWords = "tokens_per_1k_words"
        case coverageNote = "coverage_note"
    }

    /// A result this window made up because reflip could not be asked at all, or
    /// answered with something that would not decode: the same last resort
    /// `Rewriter.failure` reaches for, in the same shape a real refusal would have used,
    /// so the row that shows it does not need a second code path for "reflip never
    /// answered" versus "reflip answered no".
    static func launchFailure(model: String, reason: String) -> MeasureResult {
        MeasureResult(ok: false, model: model, reason: reason, samples: nil, errors: nil,
                      zBefore: nil, zAfter: nil, coverage: nil, editRatio: nil,
                      seconds: nil, tokensPer1kWords: nil, coverageNote: nil, verdict: nil)
    }
}
