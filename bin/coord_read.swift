// coord_read.swift — NSFileCoordinator 조율 복사 헬퍼
//
// 목적 (근본 원인 대응):
//   macOS FileProvider-backed 경로(GoogleDrive/iCloud CloudStorage)는 파일 접근에
//   NSFileCoordinator 조율을 요구한다. shutil.copy2 / /bin/cp -c(clonefile) / raw
//   read(2) 같은 "미조율 동기 접근"은 FileProvider 락과 충돌해 EDEADLK(Errno 11,
//   Resource deadlock avoided)를 낸다. 이 헬퍼는 NSFileCoordinator의 조율 읽기
//   블록 안에서 복사를 수행해 데드락 자체를 제거한다.
//
// 사용법:
//   coord_read <src> <dst>
//     src를 NSFileCoordinator 조율 하에 dst로 복사한다.
//     성공: exit 0, stderr에 "OK <bytes>"
//     실패: exit 비0, stderr에 사유
//
// 빌드:
//   swiftc -O -o bin/coord_read bin/coord_read.swift
//   (Universal 가능하면: swiftc -O -target-cpu ... 은 불필요. 아래 build 스크립트 참조.)
//
// 주의: 이 바이너리는 실서비스 Python 3.9와 무관한 별도 프로세스다.
//       조율에 실패하면 비0으로 종료하고, 호출측(core/gdrive_io.py)이 기존
//       폴백 사다리로 떨어진다 — 절대 더 나빠지지 않는다.

import Foundation

func fail(_ msg: String, _ code: Int32 = 1) -> Never {
    FileHandle.standardError.write((msg + "\n").data(using: .utf8)!)
    exit(code)
}

let args = CommandLine.arguments
guard args.count == 3 else {
    fail("usage: coord_read <src> <dst>", 2)
}

let srcPath = args[1]
let dstPath = args[2]

// macOS FS는 NFD 정규화를 쓰지만, 인자로 넘어온 경로가 NFC/NFD 어느 쪽이든
// FileManager/URL은 파일시스템 표현으로 알아서 매칭한다. 여기서는 그대로 사용.
let srcURL = URL(fileURLWithPath: srcPath)
let dstURL = URL(fileURLWithPath: dstPath)

let coordinator = NSFileCoordinator(filePresenter: nil)
var coordError: NSError?
var innerError: NSError?
var copiedBytes: Int = -1

// .withoutChanges: 읽기 전용 조율 — FileProvider가 원본을 materialize/락 해제까지
// 조율해준 뒤 블록을 실행한다. 블록 안의 URL(newURL)은 조율된 안전한 접근 지점.
coordinator.coordinate(readingItemAt: srcURL,
                        options: .withoutChanges,
                        error: &coordError) { (coordinatedURL) in
    // dst가 이미 있으면 제거 (덮어쓰기)
    if FileManager.default.fileExists(atPath: dstPath) {
        try? FileManager.default.removeItem(at: dstURL)
    }
    do {
        // 조율된 URL에서 Data로 읽어 dst에 기록.
        // copyItem 대신 read→write를 쓰는 이유: copyItem은 clonefile을 시도할 수
        // 있어 다시 미조율 경로로 샐 수 있다. Data(contentsOf:)는 조율 블록 안에서
        // 표준 read 경로를 타므로 조율 보장 안에 머문다.
        let data = try Data(contentsOf: coordinatedURL, options: [])
        try data.write(to: dstURL, options: [.atomic])
        copiedBytes = data.count
    } catch let err as NSError {
        innerError = err
    }
}

if let e = coordError {
    fail("coordinate 실패: \(e.domain) code=\(e.code) \(e.localizedDescription)", 3)
}
if let e = innerError {
    fail("복사 실패: \(e.domain) code=\(e.code) \(e.localizedDescription)", 4)
}
if copiedBytes < 0 {
    fail("복사 미수행(알 수 없음)", 5)
}

FileHandle.standardError.write("OK \(copiedBytes)\n".data(using: .utf8)!)
exit(0)
