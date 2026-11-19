// POSIX C++17 Modbus TCP client. No third-party protocol or JSON library.
#include <arpa/inet.h>
#include <cerrno>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <fcntl.h>
#include <iostream>
#include <limits>
#include <netdb.h>
#include <poll.h>
#include <stdexcept>
#include <string>
#include <sys/socket.h>
#include <unistd.h>
#include <vector>

using Bytes = std::vector<uint8_t>;
using Clock = std::chrono::steady_clock;
struct ProtocolError : std::runtime_error {
    int code;
    explicit ProtocolError(const std::string& text, int exception = 0)
        : std::runtime_error(text), code(exception) {}
};
struct Socket {
    int fd;
    explicit Socket(int value) : fd(value) {}
    ~Socket() { if (fd >= 0) ::close(fd); }
    Socket(const Socket&) = delete;
    Socket& operator=(const Socket&) = delete;
};
static void u16(Bytes& data, unsigned value) {
    data.push_back(static_cast<uint8_t>(value >> 8));
    data.push_back(static_cast<uint8_t>(value));
}
static unsigned word(const Bytes& data, size_t pos) {
    return (static_cast<unsigned>(data.at(pos)) << 8) | data.at(pos + 1);
}
static void wait_ready(int fd, short events, Clock::time_point deadline) {
    for (;;) {
        auto remaining = std::chrono::duration_cast<std::chrono::milliseconds>(deadline - Clock::now()).count();
        if (remaining <= 0) throw ProtocolError("Modbus deadline expired");
        pollfd descriptor{fd, events, 0};
        int result = ::poll(&descriptor, 1, static_cast<int>(remaining));
        if (result > 0) {
            if (descriptor.revents & events) return;
            throw ProtocolError("Modbus connection closed");
        }
        if (result == 0) throw ProtocolError("Modbus deadline expired");
        if (errno != EINTR) throw ProtocolError("Modbus poll failed");
    }
}
static Bytes receive(int fd, size_t size, Clock::time_point deadline) {
    Bytes result(size);
    size_t offset = 0;
    while (offset < size) {
        wait_ready(fd, POLLIN, deadline);
        ssize_t count = ::recv(fd, result.data() + offset, size - offset, 0);
        if (count > 0) offset += static_cast<size_t>(count);
        else if (count == 0) throw ProtocolError("truncated Modbus frame");
        else if (errno != EINTR && errno != EAGAIN && errno != EWOULDBLOCK)
            throw ProtocolError("Modbus receive failed");
    }
    return result;
}
struct Status {
    uint32_t ack, count, max_id;
    bool valve, attached, recovery, cancelled;
    double pressure;
    void print() const {
        std::cout << "{\"ack_id\":" << ack << ",\"valve\":" << (valve ? "true" : "false")
                  << ",\"pressure_kpa\":" << pressure << ",\"attached\":" << (attached ? "true" : "false")
                  << ",\"error\":\"" << (recovery ? "recovery_required" : "none")
                  << "\",\"execution_count\":" << count << ",\"max_command_id\":" << max_id
                  << ",\"cancelled\":" << (cancelled ? "true" : "false") << "}\n";
    }
};
class Client {
    std::string host, port;
    unsigned transaction = 0;
    int timeout_ms;
    Bytes request(const Bytes& pdu) {
        auto deadline = Clock::now() + std::chrono::milliseconds(timeout_ms);
        // Numeric IPv4 keeps connect/DNS inside the documented deadline.
        sockaddr_in address{};
        address.sin_family = AF_INET;
        address.sin_port = htons(static_cast<uint16_t>(std::stoul(port)));
        if (::inet_pton(AF_INET, host.c_str(), &address.sin_addr) != 1)
            throw ProtocolError("host must be a numeric IPv4 address");
        Socket sock(::socket(AF_INET, SOCK_STREAM, 0));
        if (sock.fd < 0 || ::fcntl(sock.fd, F_SETFL, O_NONBLOCK) < 0)
            throw ProtocolError("socket setup failed");
        if (::connect(sock.fd, reinterpret_cast<sockaddr*>(&address), sizeof(address)) < 0) {
            if (errno != EINPROGRESS) throw ProtocolError("Modbus connect failed");
            wait_ready(sock.fd, POLLOUT, deadline);
            int error = 0;
            socklen_t length = sizeof(error);
            if (::getsockopt(sock.fd, SOL_SOCKET, SO_ERROR, &error, &length) < 0 || error)
                throw ProtocolError("Modbus connect failed");
        }
        transaction = (transaction + 1) & 0xffff;
        Bytes frame;
        u16(frame, transaction); u16(frame, 0); u16(frame, pdu.size() + 1);
        frame.push_back(1);
        frame.insert(frame.end(), pdu.begin(), pdu.end());
        size_t offset = 0;
        while (offset < frame.size()) {
            wait_ready(sock.fd, POLLOUT, deadline);
            ssize_t count = ::send(sock.fd, frame.data() + offset, frame.size() - offset, MSG_NOSIGNAL);
            if (count > 0) offset += static_cast<size_t>(count);
            else if (count == 0 || (errno != EINTR && errno != EAGAIN && errno != EWOULDBLOCK))
                throw ProtocolError("Modbus send failed");
        }
        Bytes header = receive(sock.fd, 7, deadline);
        unsigned length = word(header, 4);
        if (word(header, 0) != transaction || word(header, 2) != 0 || header[6] != 1 || length < 2 || length > 254)
            throw ProtocolError("invalid Modbus MBAP response");
        Bytes reply = receive(sock.fd, length - 1, deadline);
        if (reply[0] == (pdu[0] | 0x80)) {
            if (reply.size() != 2) throw ProtocolError("invalid Modbus exception");
            throw ProtocolError("Modbus exception " + std::to_string(reply[1]), reply[1]);
        }
        if (reply[0] != pdu[0]) throw ProtocolError("unexpected Modbus function");
        return reply;
    }
public:
    Client(std::string h, std::string p, int timeout) : host(std::move(h)), port(std::move(p)), timeout_ms(timeout) {}
    Status status() {
        Bytes data = request({3, 0, 0, 0, 12});
        if (data.size() != 26 || data[1] != 24) throw ProtocolError("invalid status length");
        unsigned r[12];
        for (size_t i = 0; i < 12; ++i) r[i] = word(data, 2 + 2 * i);
        if (r[0] != 1 || r[3] > 1 || r[5] > 1 || r[6] > 1 || r[11] > 1)
            throw ProtocolError("invalid status values");
        int pressure = r[4] < 32768 ? static_cast<int>(r[4]) : static_cast<int>(r[4]) - 65536;
        return {(r[1] << 16) | r[2], (r[7] << 16) | r[8], (r[9] << 16) | r[10],
                r[3] != 0, r[5] != 0, r[6] != 0, r[11] != 0, pressure / 10.0};
    }
    Status operate(uint32_t id, bool cancel, bool valve) {
        Bytes pdu{16};
        u16(pdu, 100); u16(pdu, 4); pdu.push_back(8);
        u16(pdu, id >> 16); u16(pdu, id & 0xffff); u16(pdu, cancel ? 2 : 1); u16(pdu, valve ? 1 : 0);
        bool uncertain = false;
        try {
            Bytes response = request(pdu);
            if (response != Bytes{16, 0, 100, 0, 4}) throw ProtocolError("invalid write acknowledgement");
        } catch (const ProtocolError& error) {
            if (error.code) throw;
            uncertain = true;
        }
        Status result = status();
        if (uncertain && (result.recovery || result.ack != id ||
                          (cancel ? !result.cancelled : (result.cancelled || result.valve != valve))))
            throw ProtocolError("uncertain command: reconcile the same ID; do not use a new ID");
        return result;
    }
};
static uint32_t number(const std::string& text, uint32_t max) {
    if (text.empty() || text.find_first_not_of("0123456789") != std::string::npos)
        throw std::runtime_error("expected unsigned decimal integer");
    unsigned long long value = std::stoull(text);
    if (value == 0 || value > max) throw std::runtime_error("integer out of range");
    return static_cast<uint32_t>(value);
}
int main(int argc, char** argv) {
    try {
        if (argc < 4) throw std::runtime_error("usage: modbus_client IPv4 PORT status | command ID 0|1 | cancel ID");
        number(argv[2], 65535);
        Client client(argv[1], argv[2], 200);
        std::string operation = argv[3];
        if (operation == "status" && argc == 4) client.status().print();
        else if (operation == "command" && argc == 6) {
            std::string valve = argv[5];
            if (valve != "0" && valve != "1") throw std::runtime_error("valve must be 0 or 1");
            client.operate(number(argv[4], std::numeric_limits<uint32_t>::max()), false, valve == "1").print();
        } else if (operation == "cancel" && argc == 5)
            client.operate(number(argv[4], std::numeric_limits<uint32_t>::max()), true, false).print();
        else throw std::runtime_error("invalid operation or arguments");
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
