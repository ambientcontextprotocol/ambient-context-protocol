import Foundation

// Chrome's native messaging: each message is JSON in UTF-8, preceded by
// its length as 32 bits in the machine's byte order. Chrome accepts at
// most 1 MB from a host and sends at most 64 MiB to one.

public enum NativeMessage {
    public static let maxToBrowser = 1_048_576
    public static let maxFromBrowser = 64 * 1_048_576

    public enum Failure: Error, Equatable {
        // A length no browser sends: the stream is not native messaging,
        // or has lost its place, and nothing after it can be trusted.
        case tooLong(Int)
    }

    /// One message ready to write, or nil for a body the browser would
    /// refuse.
    public static func frame(_ body: Data) -> Data? {
        guard body.count <= maxToBrowser else { return nil }
        var length = UInt32(body.count)
        var framed = Data(bytes: &length, count: 4)
        framed.append(body)
        return framed
    }

    /// Takes bytes as they arrive and gives back whole messages.
    public struct Reader {
        private var buffer = Data()

        public init() {}

        public mutating func append(_ bytes: Data) { buffer.append(bytes) }

        /// The next whole message, or nil until more bytes arrive.
        public mutating func next() throws -> Data? {
            guard buffer.count >= 4 else { return nil }
            var length: UInt32 = 0
            withUnsafeMutableBytes(of: &length) { $0.copyBytes(from: buffer.prefix(4)) }
            let count = Int(length)
            guard count <= maxFromBrowser else { throw Failure.tooLong(count) }
            guard buffer.count >= 4 + count else { return nil }
            let body = buffer.subdata(in: (buffer.startIndex + 4)..<(buffer.startIndex + 4 + count))
            buffer = buffer.subdata(in: (buffer.startIndex + 4 + count)..<buffer.endIndex)
            return body
        }
    }
}
