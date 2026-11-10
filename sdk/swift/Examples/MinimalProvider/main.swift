import AmbientContextProvider
import Foundation

// The least a provider can be: one item, no positions. Run it, and a host
// or any MCP client given the endpoint and token it prints can read
// `ambient://current`. A real app does the same three things: implement
// `ContextProvider`, start a `ContextServer` when the user turns the
// feature on, and stop it on quit.
//
// A command-line program is never the app in front, so a host that asks
// only the frontmost app will not ask this one. It is here to be read and
// to be tried with a client.

@MainActor
final class Notes: ContextProvider {
    func current() -> ContextCurrent {
        ContextCurrent(focus: ["note-1"], items: [
            ContextItem(id: "note-1", type: "note", title: "Groceries", content: [.text("Eggs, rice, limes")]),
        ])
    }
}

let notes = Notes()
let server = ContextServer(
    provider: notes,
    app: ContextApp(id: "org.example.minimal-provider", name: "Minimal Provider", version: "0.1")
)
server.start()

// Remove the descriptor when stopped with Control-C.
signal(SIGINT, SIG_IGN)
let interrupt = DispatchSource.makeSignalSource(signal: SIGINT, queue: .main)
interrupt.setEventHandler {
    MainActor.assumeIsolated { server.stop() }
    exit(0)
}
interrupt.resume()

DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) {
    MainActor.assumeIsolated {
        print("endpoint: \(server.endpoint?.absoluteString ?? "not listening")")
        print("token:    \(server.token ?? "")")
        print("pid:      \(ProcessInfo.processInfo.processIdentifier)")
    }
}
RunLoop.main.run()
