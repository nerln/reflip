import AppKit
import SwiftUI

/// The entry point exists for one line that has to run before AppKit reads the command
/// line.
///
/// AppKit takes argv as pairs of a default and its value and hands whatever is left over
/// to the application as files to open. `--sample` takes no value, so it swallowed
/// `--shot` as one and left the path to the picture over: the app was launched as though
/// somebody had asked it to open a PNG, which a window group cannot answer, and it came
/// up with no window at all. It sat there, active, with nothing on screen, and the
/// unattended shot photographed nothing for a quarter of an hour before the trace in
/// WindowShot said what was happening. The same default is in Info.plist, which is where
/// it is documented; on this machine only the registration below takes effect.
@main
struct Entry {
    static func main() {
        UserDefaults.standard.register(defaults: ["NSTreatUnknownArgumentsAsOpen": false])
        ReflipApp.main()
    }
}

struct ReflipApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var delegate
    // Apps get environment actions the same as views do; this is what lets a Commands
    // button and the server strip's own button open the same window by its id instead
    // of each keeping a reference to an `NSWindow`.
    @Environment(\.openWindow) private var openWindow

    var body: some Scene {
        WindowGroup("reflip") {
            ContentView()
        }
        .windowToolbarStyle(.unified)
        // Tall rather than wide. The window is one column and what a person reads down
        // it is the text going in, what will be done to it, the text coming out, and
        // what that cost. None of those wants the width; all of them want the height.
        .defaultSize(width: 760, height: 900)
        .commands {
            CommandGroup(replacing: .newItem) { }
            // The three things this window does. Shift is not decoration: command-R is
            // Refresh in every Mac application, and starting a rewrite that spends a
            // minute of the machine by reaching for it would be the wrong way round.
            CommandMenu("Rewrite") {
                Button("Rewrite it") { post(.reflipRewrite) }
                    .keyboardShortcut("r", modifiers: [.command, .shift])
                Button("Stop") { post(.reflipStop) }
                    .keyboardShortcut(".", modifiers: .command)
                Divider()
                Button("Refresh the server") { post(.reflipRefresh) }
                    .keyboardShortcut("r", modifiers: .command)
                Divider()
                Button("Models...") { openWindow(id: "models") }
                    .keyboardShortcut("m", modifiers: [.command, .shift])
            }
            // Only when REFLIP_SHOTS says where to put them. An application that offers
            // to photograph itself in the File menu of an ordinary install is answering
            // a question nobody asked.
            if Shot.isEnabled {
                CommandGroup(after: .saveItem) {
                    Button("Save window as PNG") { Shot.save() }
                        .keyboardShortcut("p", modifiers: [.command, .option])
                }
            }
        }

        // A `Window`, not another `WindowGroup`: exactly one Models window can be open
        // at a time, and asking for it a second time brings the existing one forward
        // instead of opening a duplicate that would race the first over the one
        // download or measurement slot.
        Window("Models", id: "models") {
            ModelsWindow()
        }
        .defaultSize(width: 820, height: 680)

        Settings {
            SettingsView()
        }
    }

    private func post(_ name: Notification.Name) {
        NotificationCenter.default.post(name: name, object: nil)
    }
}

extension Notification.Name {
    /// Posted by the menu. The window listens, and the menu items know nothing about
    /// the text or the server.
    static let reflipRewrite = Notification.Name("dev.nerelli.reflip.rewrite")
    static let reflipStop = Notification.Name("dev.nerelli.reflip.stop")
    static let reflipRefresh = Notification.Name("dev.nerelli.reflip.refresh")
    /// Posted by the Models window with the chosen ref as `object`, when "Use this one"
    /// is pressed there. The main window listens and updates its own picker; the two
    /// windows otherwise share no state, so this is how a choice made in one reaches
    /// the other without a live reference passed between them.
    static let reflipModelChosen = Notification.Name("dev.nerelli.reflip.modelChosen")
}

/// Exists for two lines, both about a child process.
final class AppDelegate: NSObject, NSApplicationDelegate {
    /// Every window with a child process to clean up appends its own closure here on
    /// appearing, rather than the single slot this used to be: the Models window can be
    /// open at the same time as the main one, each with its own download or
    /// measurement in flight, and quitting has to take all of them with it, not just
    /// whichever window set this last.
    @MainActor static var onQuitHandlers: [() -> Void] = []

    func applicationDidFinishLaunching(_ notification: Notification) {
        // The text goes into the child through a pipe, and Stop kills the child while
        // that write is still in flight. The default action for the SIGPIPE that
        // follows is to kill this process too: pressing Stop on a long text took the
        // window down with the rewrite, which looked exactly like a crash because it
        // was one.
        signal(SIGPIPE, SIG_IGN)
        // The picture, when one was asked for. Here rather than in the window, because
        // the window is what has to be photographed and waiting for it to say it has
        // appeared is how the first attempt hung.
        Shot.begin()
    }

    /// Nothing here opens documents. Answering the request instead of leaving it to
    /// NSDocumentController is the second half of the argument problem described above:
    /// a launch that carried a stray argument then goes on to make its window rather
    /// than stopping at an error about a file type nobody asked about.
    func application(_ application: NSApplication, open urls: [URL]) { }

    func applicationWillTerminate(_ notification: Notification) {
        // Quitting has to take every child with it. A terminated app leaves reflip
        // running with a model resident and no window left to say what is holding the
        // memory, whether that download or measurement was started from the main
        // window or the Models one.
        MainActor.assumeIsolated {
            for handler in AppDelegate.onQuitHandlers { handler() }
        }
    }
}

/// Where the command is, where the server is, and which model to use.
///
/// Three settings, and all three are answers to "the window says it cannot find
/// something". Nothing about how a rewrite works is here: that belongs to reflip, and a
/// second place to configure it would be a second set of defaults to disagree with.
struct SettingsView: View {
    @State private var path = Cli.path
    @State private var url = Cli.serverUrl
    @State private var model = Cli.model

    var body: some View {
        Form {
            Section("The reflip command") {
                TextField("Path", text: $path)
                    .onChange(of: path) { _, value in Cli.path = value }
                Text(found)
                    .font(.caption)
                    .foregroundStyle(FileManager.default.isExecutableFile(atPath: path)
                                     ? Color.secondary : Color.red)
                Text("This window runs that command and shows what it answers. Anything "
                     + "it does here can be done in a terminal, and nothing it does is "
                     + "decided here.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Section("The model server") {
                TextField("Address", text: $url)
                    .onChange(of: url) { _, value in Cli.serverUrl = value }
                TextField("Model", text: $model)
                    .onChange(of: model) { _, value in Cli.model = value }
                Text("Left empty, the model is whichever one reflip recommends. The "
                     + "address is passed to reflip in its environment as "
                     + "REFLIP_BASE_URL, so a terminal on this Mac and this window "
                     + "reach the same server.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .formStyle(.grouped)
        .frame(width: 520, height: 360)
    }

    private var found: String {
        FileManager.default.isExecutableFile(atPath: path)
            ? "Found."
            : "Nothing runnable there. reflip installs to ~/.local/bin/reflip with pip, "
            + "and a clone has it at bin/reflip."
    }
}
