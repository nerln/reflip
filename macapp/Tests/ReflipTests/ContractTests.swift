import XCTest
@testable import Reflip

/// The window is a renderer for documents another program writes, and a reader of the
/// pipe it writes them down. Those are the two things worth testing: the shapes below
/// are the ones in the CLI contract, copied rather than paraphrased, so that a field
/// that changes name fails here before it fails on screen.
final class ContractTests: XCTestCase {

    // MARK: - `reflip server status --json`

    private let statusLine = """
    {"v":1,"ready":true,"reason":null,"message":"The model server is up at http://localhost:11434.","model":"qwen3:4b-instruct-2507-q4_K_M","server":{"url":"http://localhost:11434","installed":true,"running":true,"ours":false,"version":"0.12.4","reason":null,"models":[{"name":"qwen3:4b-instruct-2507-q4_K_M","size":2600000000,"family":"qwen3"}],"loaded":["qwen3:4b-instruct-2507-q4_K_M"]},"machine":{"total":17179869184,"free_for_work":10186539008,"pressure":1,"swap_used":0,"cores":4,"workers":2,"reasons":["Xcode is holding 3.2GB, so the budget is smaller than the free memory suggests."]}}
    """

    private func status() throws -> ServerStatus {
        try JSONDecoder().decode(ServerStatus.self, from: Data(statusLine.utf8))
    }

    func testTheServerStatusIsReadWhole() throws {
        let status = try status()
        XCTAssertTrue(status.ready)
        XCTAssertNil(status.reason)
        XCTAssertEqual(status.model, "qwen3:4b-instruct-2507-q4_K_M")
        XCTAssertEqual(status.server.url, "http://localhost:11434")
        XCTAssertEqual(status.server.version, "0.12.4")
        XCTAssertFalse(status.server.ours)
        XCTAssertEqual(status.server.models.count, 1)
        XCTAssertEqual(status.server.models.first?.size, 2_600_000_000)
        XCTAssertEqual(status.server.loaded, ["qwen3:4b-instruct-2507-q4_K_M"])
        XCTAssertEqual(status.machine.freeForWork, 10_186_539_008)
        XCTAssertEqual(status.machine.workers, 2)
        XCTAssertEqual(status.machine.reasons.count, 1)
    }

    /// The state the strip most has to survive. Ollama absent means the two lists have
    /// nothing to say, and requiring them turned "ollama is not installed" into "the
    /// window could not read the answer".
    func testAMacWithoutOllamaStillDecodes() throws {
        let line = """
        {"v":1,"ready":false,"reason":"Ollama is not installed on this Mac. Install it from ollama.com, or point reflip at any OpenAI-compatible endpoint.","message":"Ollama is not installed on this Mac.","model":"qwen3:4b-instruct-2507-q4_K_M","server":{"url":"http://localhost:11434","installed":false,"running":false,"ours":false,"version":null,"reason":"Nothing answers on port 11434 and there is no ollama on the path."},"machine":{"total":17179869184,"free_for_work":10186539008,"pressure":1,"swap_used":0,"cores":4,"workers":2,"reasons":[]}}
        """
        let status = try JSONDecoder().decode(ServerStatus.self, from: Data(line.utf8))
        XCTAssertFalse(status.ready)
        XCTAssertFalse(status.server.installed)
        XCTAssertNil(status.server.version)
        XCTAssertTrue(status.server.models.isEmpty)
        XCTAssertTrue(status.server.loaded.isEmpty)
        XCTAssertTrue(status.reason?.hasPrefix("Ollama is not installed") == true)
    }

    /// The shape the command line actually printed on the day this window was written,
    /// which is not quite the shape the contract described: no `message`, and a machine
    /// block of zeroes because memory was not read. Requiring that one string turned a
    /// server that was up, with the model on the disk, into "reflip exited with code 0
    /// and said nothing" across the whole strip.
    func testAStatusWithNoMessageStillSaysSomething() throws {
        let line = """
        {"v": 1, "ready": true, "reason": null, "model": "qwen3:4b-instruct-2507-q4_K_M", "server": {"url": "http://localhost:11434", "installed": true, "running": true, "ours": false, "version": "0.32.14", "reason": null, "models": [{"name": "qwen3:8b", "size": 5225388164, "family": "qwen3"}, {"name": "qwen3:4b-instruct-2507-q4_K_M", "size": 2497293803, "family": "qwen3"}], "loaded": []}, "machine": {"total": 0, "free_for_work": 0, "pressure": 1, "swap_used": 0, "cores": 5, "workers": 2, "reasons": ["Memory was not read on this platform, so nothing is being held back."]}}
        """
        let status = try JSONDecoder().decode(ServerStatus.self, from: Data(line.utf8))
        XCTAssertNil(status.message)
        XCTAssertTrue(status.ready)
        XCTAssertEqual(status.sentence, "The model server is up at http://localhost:11434.")
        XCTAssertTrue(status.has("qwen3:4b-instruct-2507-q4_K_M"))
        XCTAssertEqual(status.machine.reasons.count, 1)
    }

    /// Ollama prints the long name and a person types the short one. Comparing the
    /// strings as they arrive said "not downloaded" about a model that was there, and
    /// offered to download it a second time.
    func testAModelIsFoundWhateverTagItCarries() throws {
        let status = try status()
        XCTAssertTrue(status.has("qwen3:4b-instruct-2507-q4_K_M"))
        XCTAssertFalse(status.has("llama3.2"))
        XCTAssertEqual(ServerStatus.tagged("llama3.2"), "llama3.2:latest")
        XCTAssertEqual(ServerStatus.tagged("llama3.2:1b"), "llama3.2:1b")
    }

    // MARK: - `reflip rewrite --json`

    func testTheReceiptIsReadWhole() throws {
        let line = """
        {"v":1,"transform":"paraphrase","model":"qwen3:4b-instruct-2507-q4_K_M","text":"the rewritten text","words":312,"edits":231,"edit_ratio":0.74,"coverage":0.97,"llm_calls":8,"prompt_tokens":1820,"completion_tokens":700,"seconds":16.4,"notes":{"retried":1}}
        """
        let receipt = try JSONDecoder().decode(Receipt.self, from: Data(line.utf8))
        XCTAssertEqual(receipt.transform, "paraphrase")
        XCTAssertEqual(receipt.text, "the rewritten text")
        XCTAssertEqual(receipt.words, 312)
        XCTAssertEqual(receipt.edits, 231)
        XCTAssertEqual(receipt.editRatio, 0.74, accuracy: 0.0001)
        XCTAssertEqual(receipt.coverage ?? 0, 0.97, accuracy: 0.0001)
        XCTAssertEqual(receipt.llmCalls, 8)
        XCTAssertEqual(receipt.tokens, 2520)
        XCTAssertEqual(receipt.seconds, 16.4, accuracy: 0.0001)
    }

    /// Null coverage is not zero coverage, and the strip must never draw it as zero:
    /// zero means the detector recomputes every position it saw before, which is the
    /// one result worth shouting about.
    func testCoverageThatWasNotMeasuredIsNotZero() throws {
        let line = """
        {"v":1,"transform":"paraphrase","model":"qwen3:4b","text":"x","words":10,"edits":7,"edit_ratio":0.7,"coverage":null,"llm_calls":1,"prompt_tokens":80,"completion_tokens":40,"seconds":1.2}
        """
        let receipt = try JSONDecoder().decode(Receipt.self, from: Data(line.utf8))
        XCTAssertNil(receipt.coverage)
        XCTAssertEqual(receipt.tokens, 120)
    }

    /// The sentence saying why coverage is null is reflip's, and the strip must show
    /// that sentence rather than one word made up here for every cause alike.
    func testCoverageNoteCarriesReflipsOwnReason() throws {
        let line = """
        {"v":1,"transform":"paraphrase","model":"qwen3:4b","text":"x","words":10,"edits":7,"edit_ratio":0.7,"coverage":null,"coverage_note":"Coverage was not measured because no tokenizer was named.","llm_calls":1,"prompt_tokens":80,"completion_tokens":40,"seconds":1.2}
        """
        let receipt = try JSONDecoder().decode(Receipt.self, from: Data(line.utf8))
        XCTAssertNil(receipt.coverage)
        XCTAssertEqual(receipt.coverageNote,
                       "Coverage was not measured because no tokenizer was named.")
    }

    /// The two transforms that never open a socket have nothing to report about one,
    /// so the counters are absent rather than zero. Requiring them made the two
    /// cheapest transforms the two that failed to decode.
    func testATransformWithNoModelStillDecodes() throws {
        let line = """
        {"v":1,"transform":"unicode","model":null,"text":"x","words":10,"edits":0,"edit_ratio":0.0,"coverage":null,"seconds":0.01}
        """
        let receipt = try JSONDecoder().decode(Receipt.self, from: Data(line.utf8))
        XCTAssertNil(receipt.model)
        XCTAssertEqual(receipt.llmCalls, 0)
        XCTAssertEqual(receipt.tokens, 0)
        XCTAssertEqual(receipt.transform, "unicode")
    }

    func testARefusalCarriesItsSentence() throws {
        let line = """
        {"v":1,"ok":false,"reason":"No model server is running, so there is nothing to rewrite with."}
        """
        let refusal = try JSONDecoder().decode(Refusal.self, from: Data(line.utf8))
        XCTAssertEqual(refusal.sentence,
                       "No model server is running, so there is nothing to rewrite with.")
    }

    // MARK: - the lines a running command writes

    func testProgressAndDownloadLinesDecode() {
        let progress = Event.from(
            #"{"event":"progress","phase":"Rewriting","done":3,"total":8,"message":"Rewriting paragraph 3 of 8"}"#)
        XCTAssertEqual(progress?.phase, "Rewriting")
        XCTAssertEqual(progress?.message, "Rewriting paragraph 3 of 8")
        XCTAssertEqual(progress?.fraction ?? 0, 0.375, accuracy: 0.0001)

        let pull = Event.from(
            #"{"event":"pull","status":"pulling manifest","completed":123,"total":456}"#)
        XCTAssertEqual(pull?.status, "pulling manifest")
        XCTAssertEqual(pull?.completed, 123)

        // Both may be null before the download has a size, and a bar drawn from a zero
        // total sits at the far left and reads as a download that is stuck.
        let starting = Event.from(#"{"event":"pull","status":"pulling manifest","completed":null,"total":null}"#)
        XCTAssertNotNil(starting)
        XCTAssertNil(starting?.completed)
        XCTAssertNil(starting?.fraction)

        let done = Event.from(#"{"event":"done","ok":true,"message":"The model is on this Mac."}"#)
        XCTAssertEqual(done?.event, "done")
        XCTAssertEqual(done?.ok, true)

        // Anything else on stderr is a warning from a library reflip imports.
        XCTAssertNil(Event.from("UserWarning: torch was compiled without flash attention"))
    }

    // MARK: - reading the pipe

    /// The bug this exists for: a pipe hands over bytes, not lines. Splitting each
    /// chunk as though it were whole lost the half of the line carrying the event name,
    /// and a rewrite that takes a minute never ticked.
    func testALineCutInHalfIsPutBackTogether() {
        var reader = LineReader()
        XCTAssertTrue(reader.feed(#"{"event":"progress","phase":"Rewri"#).isEmpty)

        let lines = reader.feed("""
        ting","done":3,"total":8}
        {"event":"progress","phase":"Rewriting","done":4,"total":8}
        {"event":"progress","phase":"Che
        """)
        XCTAssertEqual(lines.count, 2)
        XCTAssertEqual(Event.from(lines[0])?.done, 3)
        XCTAssertEqual(Event.from(lines[1])?.done, 4)

        // The third line is incomplete and is held back rather than decoded in half.
        XCTAssertTrue(reader.feed("").isEmpty)
        let tail = reader.feed("cking\",\"done\":8,\"total\":8}\n")
        XCTAssertEqual(tail.count, 1)
        XCTAssertEqual(Event.from(tail[0])?.phase, "Checking")
    }

    /// A program that dies does not always end its last line with a newline, and the
    /// reason it died is on that line.
    func testWhatIsLeftOverIsNotLost() {
        var reader = LineReader()
        XCTAssertTrue(reader.feed("No model server is running.").isEmpty)
        XCTAssertEqual(reader.flush(), ["No model server is running."])
        XCTAssertTrue(reader.flush().isEmpty)
    }

    /// The receipt is the last line, and the libraries reflip imports print warnings
    /// above it. Decoding the whole buffer failed on the warning while the answer sat
    /// on the line below.
    func testTheAnswerIsTheLastLineWithAnythingOnIt() throws {
        let printed = """
        UserWarning: resource_tracker found 1 leaked semaphore

        {"v":1,"transform":"rules","model":null,"text":"x","words":2,"edits":1,"edit_ratio":0.5,"coverage":null,"seconds":0.02}

        """
        guard let body = Cli.lastLine(of: Data(printed.utf8)) else {
            return XCTFail("nothing came back")
        }
        let receipt = try JSONDecoder().decode(Receipt.self, from: body)
        XCTAssertEqual(receipt.transform, "rules")
        XCTAssertNil(Cli.lastLine(of: Data("\n  \n".utf8)))
    }

    // MARK: - finding the command

    /// An application started from the Dock inherits a PATH with neither ~/.local/bin
    /// nor /opt/homebrew/bin on it, so the window found nothing while the same command
    /// worked in every terminal on the machine.
    func testTheCommandIsFoundOffTheInheritedPath() {
        let found = Cli.discover(environment: ["PATH": "/usr/bin:/bin"],
                                 home: "/Users/x", beside: "/repo/bin/reflip",
                                 isExecutable: { $0 == "/opt/homebrew/bin/reflip" })
        XCTAssertEqual(found, "/opt/homebrew/bin/reflip")
    }

    func testAPathEntryIsTriedFirst() {
        let found = Cli.discover(environment: ["PATH": "/a:/b"],
                                 home: "/Users/x", beside: "/repo/bin/reflip",
                                 isExecutable: { $0 == "/b/reflip" || $0 == "/usr/bin/reflip" })
        XCTAssertEqual(found, "/b/reflip")
    }

    /// A clone that was never installed: the app sits in macapp/ and the command sits
    /// in bin/ beside it.
    func testACloneIsTheLastPlaceLookedAt() {
        let found = Cli.discover(environment: ["PATH": "/usr/bin"],
                                 home: "/Users/x", beside: "/repo/bin/reflip",
                                 isExecutable: { $0 == "/repo/bin/reflip" })
        XCTAssertEqual(found, "/repo/bin/reflip")
    }

    /// Somebody who set REFLIP_BIN is better served by "nothing runnable at the path
    /// you gave" than by a window that quietly used a different reflip.
    func testAnExplicitPathWinsEvenWhenItIsWrong() {
        let found = Cli.discover(environment: ["REFLIP_BIN": "/opt/mine/reflip",
                                               "PATH": "/usr/bin"],
                                 home: "/Users/x", beside: "/repo/bin/reflip",
                                 isExecutable: { _ in true })
        XCTAssertEqual(found, "/opt/mine/reflip")
    }

    /// With nothing runnable anywhere, the answer still has to be a path worth naming
    /// in the sentence that says it is missing.
    func testWithNothingInstalledItNamesWherePipPutsIt() {
        let found = Cli.discover(environment: [:], home: "/Users/x",
                                 beside: "/repo/bin/reflip", isExecutable: { _ in false })
        XCTAssertEqual(found, "/Users/x/.local/bin/reflip")
    }

    // MARK: - the same numbers the terminal prints

    func testSizesAreWrittenTheWayReflipWritesThem() {
        XCTAssertEqual(Format.bytes(2_684_354_560), "2.5GB")
        XCTAssertEqual(Format.bytes(512 * 1024 * 1024), "512.0MB")
        XCTAssertEqual(Format.bytes(0), "0B")
        XCTAssertEqual(Format.percent(0.74), "74%")
        XCTAssertEqual(Format.percent(0.035), "4%")
        XCTAssertEqual(Format.seconds(16.42), "16.4")
        XCTAssertEqual(Format.zScore(18.01), "18.0")
        // Unwatermarked text can score a little below zero; a z-score is the one figure
        // in this window that a negative sign is a real, good result rather than a bug.
        XCTAssertEqual(Format.zScore(-0.288), "-0.3")
        XCTAssertEqual(Format.gigabytes(2.5), "2.5 GB")
    }

    /// The labels are sentences a person reads before pressing the button, so they are
    /// part of the contract rather than decoration.
    func testTheFourKnownTransformsHaveTheirOwnSentence() {
        XCTAssertTrue(TransformCatalogue.takesStride("infill"))
        XCTAssertTrue(TransformCatalogue.takesStride("hybrid"))
        XCTAssertFalse(TransformCatalogue.takesStride("paraphrase"))
        XCTAssertFalse(TransformCatalogue.needsModel("rules"))
        XCTAssertFalse(TransformCatalogue.needsModel("unicode"))
        XCTAssertTrue(TransformCatalogue.needsModel("hybrid"))
        XCTAssertEqual(TransformCatalogue.label(for: "unicode"),
                       "Strip invisible characters only (does nothing to the watermark)")
        XCTAssertEqual(TransformCatalogue.label(for: "paraphrase"),
                       "Rewrite every paragraph (best result)")
    }

    /// A transform this window has never heard of still gets a readable label rather
    /// than disappearing from the picker or showing raw command-line spelling: this is
    /// the whole point of reading the list from `reflip transforms` instead of
    /// compiling it in.
    func testAnUnknownTransformFallsBackToItsTitleCasedName() {
        XCTAssertEqual(TransformCatalogue.label(for: "hybrid"), "Hybrid")
        XCTAssertEqual(TransformCatalogue.label(for: "future_transform"), "Future Transform")
        XCTAssertFalse(TransformCatalogue.takesStride("future_transform"))
        XCTAssertTrue(TransformCatalogue.needsModel("future_transform"))
    }

    // MARK: - `reflip transforms --json`

    /// The shape a real run printed: `reflip transforms --json` on this machine, with
    /// no transforms of the person's own.
    func testTransformsResponseIsReadWhole() throws {
        let line = """
        {"v": 1, "transforms": ["hybrid", "infill", "paraphrase", "rules", "unicode"], "local_dir": "/Users/eugenionerelli/.reflip/transforms", "local_errors": {}}
        """
        let parsed = try JSONDecoder().decode(TransformsResponse.self, from: Data(line.utf8))
        XCTAssertEqual(parsed.transforms, ["hybrid", "infill", "paraphrase", "rules", "unicode"])
        XCTAssertEqual(parsed.localDir, "/Users/eugenionerelli/.reflip/transforms")
        XCTAssertTrue(parsed.localErrors.isEmpty)
    }

    /// A person's own transform file that did not load: silence about it would look
    /// exactly like a transform they never wrote, which is why the window is expected
    /// to compose reflip's own path, file name and sentence into one line rather than
    /// drop the entry.
    func testATransformFileThatDidNotLoadCarriesItsOwnSentence() throws {
        let line = """
        {"v": 1, "transforms": ["infill", "paraphrase", "rules", "unicode"], "local_dir": "/Users/eugenionerelli/.reflip/transforms", "local_errors": {"my_transform.py": "SyntaxError: invalid syntax (my_transform.py, line 4)"}}
        """
        let parsed = try JSONDecoder().decode(TransformsResponse.self, from: Data(line.utf8))
        XCTAssertEqual(parsed.localErrors["my_transform.py"],
                       "SyntaxError: invalid syntax (my_transform.py, line 4)")
        XCTAssertFalse(parsed.transforms.contains("my_transform"))
    }

    // MARK: - `reflip models --recommended --json`

    func testTheCatalogueIsReadWhole() throws {
        let line = """
        {"v":1,"recommended":[{"ref":"qwen3:4b-instruct-2507-q4_K_M","params":"4B","size_gb":2.5,"good_at":"Fluent English at a speed that keeps a rewrite under twenty seconds.","watch_out":"Its Italian is noticeably weaker than its English.","languages":"English well, other European languages adequately","measured":"24 watermarked texts: detector z from 17.6 to 0.28.","watermarks":false,"source":"ollama","tags":["default","fast"],"installed":true},{"ref":"gemma3:4b","params":"4B","size_gb":3.3,"good_at":"Stronger on languages other than English.","watch_out":"Google watermarks the Gemini service, not these open weights.","languages":"Strong multilingual","measured":null,"watermarks":false,"source":"ollama","tags":["multilingual"],"installed":false}],"default":"qwen3:4b-instruct-2507-q4_K_M","installed":["qwen3:4b-instruct-2507-q4_K_M"],"server_reason":null}
        """
        let recommended = try JSONDecoder().decode(RecommendedModels.self, from: Data(line.utf8))
        XCTAssertEqual(recommended.recommended.count, 2)
        XCTAssertEqual(recommended.defaultModel, "qwen3:4b-instruct-2507-q4_K_M")
        XCTAssertTrue(recommended.recommended[0].installed)
        XCTAssertFalse(recommended.recommended[1].installed)
        XCTAssertEqual(recommended.recommended[0].sizeGB, 2.5, accuracy: 0.0001)
        XCTAssertEqual(recommended.recommended[0].measured,
                       "24 watermarked texts: detector z from 17.6 to 0.28.")
        XCTAssertNil(recommended.recommended[1].measured)
        XCTAssertNil(recommended.serverReason)
    }

    /// The server could not be read at all, which the catalogue survives: the rows
    /// still decode, and the reason is carried rather than dropped.
    func testTheCatalogueSurvivesAServerThatCouldNotBeRead() throws {
        let line = """
        {"v":1,"recommended":[],"default":"qwen3:4b-instruct-2507-q4_K_M","installed":[],"server_reason":"Ollama is not installed on this Mac."}
        """
        let recommended = try JSONDecoder().decode(RecommendedModels.self, from: Data(line.utf8))
        XCTAssertTrue(recommended.recommended.isEmpty)
        XCTAssertEqual(recommended.serverReason, "Ollama is not installed on this Mac.")
    }

    // MARK: - `reflip models --search QUERY --json`

    func testSearchResultsAreReadWhole() throws {
        let line = """
        {"v":1,"query":"gemma 3","results":[{"ref":"hf.co/MaziyarPanahi/gemma-3-4b-it-GGUF:Q4_K_M","repo":"MaziyarPanahi/gemma-3-4b-it-GGUF","downloads":162779,"likes":20,"gated":false,"page":"https://huggingface.co/MaziyarPanahi/gemma-3-4b-it-GGUF","refused":null},{"ref":"hf.co/AnkitAI/Parable-Qwen3-4B-Claude-Fable-5-GGUF:Q4_K_M","repo":"AnkitAI/Parable-Qwen3-4B-Claude-Fable-5-GGUF","downloads":448624,"likes":15,"gated":false,"page":"https://huggingface.co/AnkitAI/Parable-Qwen3-4B-Claude-Fable-5-GGUF","refused":"Claude models launched since 2 August 2026 watermark their own text."}],"note":"These are search results, not recommendations."}
        """
        let search = try JSONDecoder().decode(SearchResults.self, from: Data(line.utf8))
        XCTAssertEqual(search.query, "gemma 3")
        XCTAssertEqual(search.results.count, 2)
        XCTAssertNil(search.results[0].refused)
        XCTAssertEqual(search.results[1].refused,
                       "Claude models launched since 2 August 2026 watermark their own text.")
        XCTAssertEqual(search.note, "These are search results, not recommendations.")
    }

    /// Hugging Face could not be reached at all: an empty list with a sentence saying
    /// why, not an error this window has to invent its own words for.
    func testASearchThatFoundNothingCarriesTheReason() throws {
        let line = """
        {"v":1,"query":"gemma 3","results":[],"note":"Hugging Face could not be reached: [Errno 8] nodename nor servname provided, or not known"}
        """
        let search = try JSONDecoder().decode(SearchResults.self, from: Data(line.utf8))
        XCTAssertTrue(search.results.isEmpty)
        XCTAssertTrue(search.note?.hasPrefix("Hugging Face could not be reached") == true)
    }

    // MARK: - `reflip models --measure MODEL --json`

    /// The shape a real measurement printed, copied from a live run of `reflip models
    /// --measure qwen3:4b-instruct-2507-q4_K_M --samples 1 --json` rather than made up.
    func testAMeasurementIsReadWhole() throws {
        let line = """
        {"v": 1, "ok": true, "model": "qwen3:4b-instruct-2507-q4_K_M", "samples": 1, "errors": 0, "z_before": 18.01, "z_after": -0.288, "coverage": 0.9839, "edit_ratio": 0.7983, "seconds": 23.41, "tokens_per_1k_words": 4403.0, "coverage_note": null, "rows": [{"id": "wm-000"}], "verdict": "Good for this job on this machine: the detector was left inside the range of unwatermarked text."}
        """
        let measured = try JSONDecoder().decode(MeasureResult.self, from: Data(line.utf8))
        XCTAssertTrue(measured.ok)
        XCTAssertEqual(measured.model, "qwen3:4b-instruct-2507-q4_K_M")
        XCTAssertNil(measured.reason)
        XCTAssertEqual(measured.samples, 1)
        XCTAssertEqual(measured.errors, 0)
        XCTAssertEqual(measured.zBefore ?? 0, 18.01, accuracy: 0.0001)
        XCTAssertEqual(measured.zAfter ?? 0, -0.288, accuracy: 0.0001)
        XCTAssertEqual(measured.coverage ?? 0, 0.9839, accuracy: 0.0001)
        XCTAssertEqual(measured.tokensPer1kWords ?? 0, 4403.0, accuracy: 0.0001)
        XCTAssertTrue(measured.verdict?.hasPrefix("Good for this job") == true)
        // `rows` is not decoded: the row in this window shows the aggregate figures
        // above, not a per-sample breakdown, so a field this struct never reads is not
        // a field it needs to survive a shape change in.
    }

    /// A model that watermarks its own output, or a machine with no benchmark corpus:
    /// the refusal shape carries only three fields, and every figure must come back
    /// nil rather than the decode failing on the ones that are simply missing.
    func testARefusedMeasurementCarriesOnlyItsReason() throws {
        let line = """
        {"v":1,"ok":false,"model":"claude-3-haiku","reason":"Claude models launched since 2 August 2026 watermark their own text."}
        """
        let measured = try JSONDecoder().decode(MeasureResult.self, from: Data(line.utf8))
        XCTAssertFalse(measured.ok)
        XCTAssertEqual(measured.model, "claude-3-haiku")
        XCTAssertEqual(measured.reason,
                       "Claude models launched since 2 August 2026 watermark their own text.")
        XCTAssertNil(measured.zBefore)
        XCTAssertNil(measured.zAfter)
        XCTAssertNil(measured.coverage)
        XCTAssertNil(measured.verdict)
    }

    /// Every sample errored: `ok` is false but there is no `reason`, because nothing
    /// refused the request, it just did not produce anything usable. The row has to
    /// show something other than a blank when `reason` is absent too.
    func testAMeasurementWhereEveryRowFailedIsStillNotOk() throws {
        let line = """
        {"v":1,"ok":false,"model":"broken-model","samples":1,"errors":1,"z_before":null,"z_after":null,"coverage":null,"edit_ratio":null,"seconds":null,"tokens_per_1k_words":null,"coverage_note":null,"rows":[{"id":"wm-000","error":"connection refused"}],"verdict":null}
        """
        let measured = try JSONDecoder().decode(MeasureResult.self, from: Data(line.utf8))
        XCTAssertFalse(measured.ok)
        XCTAssertNil(measured.reason)
        XCTAssertEqual(measured.errors, 1)
    }

    // MARK: - the sample the pictures are taken of

    /// A picture must not contradict itself. The window prints the word count above the
    /// text and the receipt prints it again underneath, and the sample is written as a
    /// string with line continuations in it: one lost space before a backslash joins two
    /// words, and the two counts stop agreeing in a screenshot nobody re-reads.
    func testTheSampleAgreesWithItsOwnReceipt() throws {
        let words = Shot.sampleSource.split(whereSeparator: \.isWhitespace).count
        guard let receipt = Shot.sampleReceipt() else {
            return XCTFail("the sample receipt did not decode")
        }
        XCTAssertEqual(words, 287)
        // reflip counts a hyphenated compound as two words, so its own count of this
        // paragraph is two higher than splitting on spaces. The check is that the
        // receipt was measured from this text and not from some other one, which a
        // difference of two allows and a difference of fifty does not.
        XCTAssertEqual(receipt.words, words, accuracy: 3)
        XCTAssertEqual(Double(receipt.edits) / Double(receipt.words), receipt.editRatio,
                       accuracy: 0.005)
        // The figures come from a real run, so this is a guard on the paste rather than
        // a claim about the tool: any coverage this high says the same thing.
        XCTAssertGreaterThan(receipt.coverage ?? 0, 0.95)
        XCTAssertFalse(receipt.text.isEmpty)
        XCTAssertNotEqual(receipt.text, Shot.sampleSource)
    }
}
