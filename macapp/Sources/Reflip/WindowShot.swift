import AppKit
import SwiftUI

/// Saves a PNG of this window, for the README and the site.
///
/// Two things it is not. It is not `screencapture`, which needs the screen recording
/// permission, a large thing to hand out for the sake of a picture in a README; an
/// application asking the window server for an image of its own window already owns
/// those pixels. And it is not a person clicking a menu: the pictures are made by a
/// script that opens this window, seeds it, asks for a file and quits, so regenerating
/// them after a change to the layout is one command rather than an afternoon.
///
///     REFLIP_SHOTS=1 open -W -n --env REFLIP_SHOTS=1 -a Reflip.app --args \
///         --sample --shot ../docs/img/window.png --appearance dark
///
/// `--shot-models` photographs the Models window instead of the main one, opening it
/// the same way the "Models…" button does rather than by any shortcut this file takes
/// for itself:
///
///     REFLIP_SHOTS=1 open -W -n --env REFLIP_SHOTS=1 -a Reflip.app --args \
///         --sample --shot-models --shot ../docs/img/models.png --appearance dark
///
/// With `REFLIP_SHOTS` set to a folder and no `--shot`, the File menu grows an item
/// instead and the pictures are taken by hand.
enum Shot {

    static var isEnabled: Bool { directory != nil }

    /// Whether this launch asked for a picture of the Models window rather than the
    /// main one. Read here and acted on in `ContentView`, which is the one place with
    /// an `openWindow` action to call: this enum has no view to open a window from.
    static var wantsModelsWindow: Bool {
        CommandLine.arguments.contains("--shot-models")
    }

    /// Waits for the Models window to exist, then keys and fronts it explicitly.
    ///
    /// `openWindow(id:)` alone was not enough: launched by `open` rather than by a
    /// person clicking anything, the new window came up visible but the main window
    /// stayed key, and the picture this whole file exists to take was of the wrong
    /// window every time. Polled rather than awaited once, because the window does not
    /// exist the instant `openWindow` returns; it is created a turn or two later.
    @MainActor
    static func bringModelsWindowForward() async {
        guard wantsModelsWindow else { return }
        for _ in 0..<30 {
            if let window = NSApp.windows.first(where: { $0.title == "Models" && $0.isVisible }) {
                window.makeKeyAndOrderFront(nil)
                trace("brought the Models window forward")
                return
            }
            try? await Task.sleep(nanoseconds: 100_000_000)
        }
        trace("the Models window never appeared to bring forward")
    }

    static var directory: URL? {
        guard let raw = ProcessInfo.processInfo.environment["REFLIP_SHOTS"], !raw.isEmpty
        else { return nil }
        return URL(fileURLWithPath: (raw as NSString).expandingTildeInPath)
    }

    // MARK: - the scripted form

    private static func argument(_ name: String) -> String? {
        let args = CommandLine.arguments
        guard let i = args.firstIndex(of: name), i + 1 < args.count else { return nil }
        return args[i + 1]
    }

    /// Take the picture and quit. Everything here has to happen whether or not any view
    /// ever appears, so it is driven by the application delegate.
    ///
    /// The first version of this ran from ContentView.onAppear, the way rada's does.
    /// rada is started by running the executable inside the bundle; this one is started
    /// with `open`, and launched that way the callback never arrived: the app sat in its
    /// event loop with the picture unwritten until it was killed, and stdout was going
    /// nowhere anybody could read it. The delegate is called by AppKit itself, and
    /// `trace` below is what turned that fifteen minutes into one launch.
    @MainActor
    static func begin() {
        trace("begin, arguments: \(CommandLine.arguments.dropFirst().joined(separator: " "))")
        // Pinned, because it is not the machine's business what the documentation looks
        // like. Left to the system, four shots taken one minute apart came back as two
        // light and two dark.
        switch argument("--appearance") {
        case "light": NSApp.appearance = NSAppearance(named: .aqua)
        case "dark":  NSApp.appearance = NSAppearance(named: .darkAqua)
        default:      break
        }

        guard let target = argument("--shot") else { return }

        Task { @MainActor in
            // Wait for there to be something to photograph. The `where` clause is tested
            // on every turn, so this leaves as soon as a window exists and gives up
            // after four seconds instead of hanging on a launch that went wrong.
            for _ in 0..<40 where !hasWindow {
                try? await Task.sleep(nanoseconds: 100_000_000)
            }
            // A window nobody brought forward is still drawn, but it is drawn behind
            // whatever asked for the picture, and the first shot came back with a
            // terminal in front of half of it.
            NSApp.activate(ignoringOtherApps: true)
            // Long enough for the first `reflip server status` to answer and for the
            // sample to have been seeded by the view. The Models window opens its own
            // two commands on appearing and gets extra time for both to answer, so the
            // picture is not taken of a window still saying "Asking reflip...".
            let wait: UInt64 = wantsModelsWindow ? 2_500_000_000 : 1_500_000_000
            try? await Task.sleep(nanoseconds: wait)
            let visible = NSApp.windows.filter(\.isVisible)
            trace("\(visible.count) window on screen: "
                 + visible.map { $0.title.isEmpty ? "(untitled)" : $0.title }.joined(separator: ", "))

            let url = URL(fileURLWithPath: (target as NSString).expandingTildeInPath)
            var ok = false
            for _ in 0..<10 where !ok {
                ok = write(to: url)
                if !ok { try? await Task.sleep(nanoseconds: 300_000_000) }
            }
            trace(ok ? "wrote \(url.path)" : "could not write \(url.path)")
            print(ok ? "wrote \(url.path)" : "could not write \(url.path)")
            // exit rather than terminate. The ordinary shutdown asks each window whether
            // it may close, and one that is mid-rewrite does not answer at once: the
            // picture came out fine and the process then sat there until it was killed.
            exit(ok ? 0 : 1)
        }
    }

    @MainActor
    private static var hasWindow: Bool {
        NSApp.windows.contains { $0.isVisible && $0.className != "NSStatusBarWindow" }
    }

    /// Put something in the window worth photographing.
    ///
    /// Separate from `begin` because it needs the view's own state, which the delegate
    /// has no way to reach. A shot taken before this lands is a picture of two empty
    /// boxes, which is why the capture above waits.
    @MainActor
    static func arrange(rewriter: Rewriter, source: Binding<String>) {
        guard isEnabled, CommandLine.arguments.contains("--sample") else { return }
        source.wrappedValue = sampleSource
        if let receipt = sampleReceipt() { rewriter.show(receipt) }
        trace("sample seeded")
    }

    /// A line in a file, because a picture is taken with nobody watching and stdout goes
    /// nowhere when the app is started by `open`. Only under REFLIP_SHOTS: an ordinary
    /// install writes nothing anywhere.
    private static func trace(_ line: String) {
        guard isEnabled else { return }
        let path = "/tmp/reflip-shot.log"
        let stamped = "\(Date()) \(line)\n"
        if let handle = FileHandle(forWritingAtPath: path) {
            defer { try? handle.close() }
            _ = try? handle.seekToEnd()
            try? handle.write(contentsOf: Data(stamped.utf8))
        } else {
            try? stamped.write(toFile: path, atomically: true, encoding: .utf8)
        }
    }

    // MARK: - the menu form

    @MainActor
    @discardableResult
    static func save(named name: String? = nil) -> URL? {
        guard let dir = directory else { return nil }
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        let url = dir.appendingPathComponent((name ?? nextName()) + ".png")
        guard write(to: url) else { NSSound.beep(); return nil }
        NSSound(named: "Grab")?.play()
        return url
    }

    /// PNG of the window this process owns.
    ///
    /// Asking the window server for the window's own image is the only version of this
    /// that comes back whole. Drawing the view hierarchy by hand skips whatever the
    /// compositor is responsible for, and here that is both materials, the strip at the
    /// top and the strip at the bottom, which are most of what the picture is for.
    ///
    /// The compiler says this call is deprecated in favour of ScreenCaptureKit. It is
    /// kept anyway, and the warning is the price: ScreenCaptureKit asks for the screen
    /// recording permission even to photograph the caller's own window, which is the
    /// permission this whole file exists to avoid asking for.
    @MainActor
    @discardableResult
    private static func write(to url: URL) -> Bool {
        // A save panel is a window of its own, and so is a sheet. Photographing the
        // parent alone gives a picture of the window with the panel missing, which is a
        // picture of a different program.
        let regular = NSApp.windows.filter {
            $0.isVisible && $0.sheetParent == nil && $0.className != "NSStatusBarWindow"
        }
        // `--shot-models` picks its window by title rather than by trusting an order or
        // a key state. Launched by `open` rather than by a click, this process's own
        // windows never actually became key here: `NSApp.keyWindow` measured nil at
        // capture time even right after `makeKeyAndOrderFront`, and `NSApp.windows`
        // turned out to list windows in creation order rather than front-to-back, so
        // with two regular windows open the main one was photographed every time
        // regardless of which was actually on top. Asking by title, once there can be
        // more than one regular window, is the one thing this file does not have to
        // guess about.
        let parent = wantsModelsWindow
            ? regular.first(where: { $0.title == "Models" })
            : regular.first
        guard let parent = parent ?? NSApp.keyWindow else { return false }
        let sheets = NSApp.windows.filter { $0.isVisible && $0.sheetParent === parent }
        var ids = (sheets + [parent]).map { UnsafeRawPointer(bitPattern: UInt($0.windowNumber)) }
        guard let list = CFArrayCreate(nil, &ids, ids.count, nil),
              let image = CGImage(windowListFromArrayScreenBounds: .null,
                                  windowArray: list,
                                  imageOption: [.boundsIgnoreFraming, .bestResolution])
        else { return false }
        let rep = NSBitmapImageRep(cgImage: image)
        guard let data = rep.representation(using: .png, properties: [:]) else { return false }
        try? FileManager.default.createDirectory(at: url.deletingLastPathComponent(),
                                                 withIntermediateDirectories: true)
        return (try? data.write(to: url)) != nil
    }

    /// shot-01, shot-02. Overwriting the last one silently is how a README quietly
    /// loses a picture.
    private static func nextName() -> String {
        guard let dir = directory else { return "shot" }
        let taken = (try? FileManager.default.contentsOfDirectory(atPath: dir.path)) ?? []
        for n in 1...99 {
            let candidate = String(format: "shot-%02d", n)
            if !taken.contains(candidate + ".png") { return candidate }
        }
        return "shot"
    }

    // MARK: - something for the layout to draw

    /// The text `--sample` puts in the window, and a rewrite of it.
    ///
    /// A picture of an empty window shows nothing, so this exists to fill it. It is not
    /// a measurement and nothing else in this application produces one: every number a
    /// person sees in ordinary use came out of `reflip rewrite`, and the figures below
    /// are a drawing of that receipt made by hand, kept in one place, behind a flag, so
    /// that there is exactly one file to check when somebody asks where a number in the
    /// README came from. The shares are the ones the benchmark reports for a
    /// coverage-checked paraphrase; the counts are that rate applied to this text.
    static let sampleSource = """
    Since August 2026 the text these models produce carries a watermark, and almost \
    everything written about removing it is wrong in the same way. The mark is not a \
    character hidden between the words. There is no zero-width space to strip, no curly \
    quote to straighten, no metadata field to blank. What was marked is the choice of \
    words itself: at every step the sampler weighed the candidates it could have picked \
    and leaned, very slightly, towards the ones whose hash came up on the right side of \
    a coin it had flipped in private. The bias in any one word is far too small to see. \
    Across four hundred of them it is a signal a detector can find with confidence.

    That is why the tools that promise to clean a document by deleting invisible \
    characters do nothing at all. They change bytes the detector never looks at, and \
    leave every weighted choice exactly where it was. The score before and after is the \
    same to the second decimal, which is the kind of claim that is easy to check and \
    that none of those tools publishes.

    What does work is unremarkable and expensive: rewrite the words. Each coin depends \
    on the token it belongs to and the few tokens before it, so a single replacement \
    re-randomises its own coin and the ones that follow. Change something in every \
    window of five tokens and there is nothing coherent left for the detector to \
    average. A local model does this well enough on a laptop, in about the time it takes \
    to read the result, and the only honest way to say so is to run the detector \
    yourself, before and after, and print what it said.
    """

    private static let sampleResult = """
    From August 2026 onward, the output of these models includes a stamp, and nearly all claims \
    regarding its removal are flawed in identical fashion. The imprint isn't a character slipped \
    between letters. There's no invisible gap to erase, no wiggly quotation to fix, no hidden \
    data field to wipe. What was actually marked is the selection of language itself: at each \
    point, the generation process evaluated possible choices and subtly favored those whose hash \
    landed on the positive side of a private coin toss. The deviation in any single word is \
    utterly negligible. Over four hundred words, however, this pattern forms a detectable \
    signal.

    That's exactly why any tool claiming to purify a file by removing hidden symbols fails \
    completely. It alters bytes the scanner simply ignores, and preserves each significant \
    decision precisely as it was. The result remains unchanged to the hundredth place, a detail \
    anyone can verify—yet no such tool ever shares this data.

    What functions is dull and costly: rephrase the phrases. Each piece relies on the token it \
    connects to and the earlier tokens, meaning one edit reshuffles its own value and all \
    subsequent ones. Modify any segment of five tokens and coherence vanishes for the scanner to \
    interpret. A small model handles this efficiently on a laptop, matching the duration it \
    takes to view the output, and the only truthful way to confirm it is to execute the scanner \
    both before and after, and display its findings.
    """

    /// Built as JSON and read back through the same decoder a real answer goes through,
    /// so that a picture cannot show a receipt reflip could not have printed.
    static func sampleReceipt() -> Receipt? {
        // Measured, not drawn. These are what `reflip rewrite` printed for the paragraph
        // above on 3 September 2026, with the model named below on this laptop. A picture
        // of a receipt is a claim, and this repository's whole argument is that a claim
        // about a detector has to be one somebody ran.
        let fields: [String: Any] = [
            "v": 1,
            "transform": "paraphrase",
            "model": "qwen3:4b-instruct-2507-q4_K_M",
            "text": sampleResult,
            "words": 289,
            "edits": 196,
            "edit_ratio": 0.6782,
            "coverage": 0.9894,
            "llm_calls": 3,
            "prompt_tokens": 651,
            "completion_tokens": 305,
            "seconds": 13.65,
        ]
        guard let data = try? JSONSerialization.data(withJSONObject: fields) else { return nil }
        return try? JSONDecoder().decode(Receipt.self, from: data)
    }
}
