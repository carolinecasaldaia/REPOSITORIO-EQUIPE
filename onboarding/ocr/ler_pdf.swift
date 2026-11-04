// Lê o texto de um PDF digitalizado usando o OCR do próprio macOS (Vision).
//
// Por que assim, e não com Tesseract: esta máquina não tem Homebrew, e o
// reconhecimento da Apple é melhor em português — é o mesmo que a Visualização
// usa quando você seleciona texto numa foto. Zero dependência de terceiros:
// PDFKit e Vision já vêm no sistema.
//
// Uso:  ler-pdf <arquivo> [máximo de páginas]
// Aceita PDF e também foto (jpg, png, heic) — metade dos documentos que os
// clientes mandam pelo WhatsApp é foto de papel.
// Sai 0 com o texto na saída padrão; 2 quando não consegue abrir o arquivo.

import AppKit
import Foundation
import PDFKit
import Vision

let argumentos = CommandLine.arguments
guard argumentos.count > 1 else {
    FileHandle.standardError.write("uso: ler-pdf <arquivo> [páginas]\n".data(using: .utf8)!)
    exit(2)
}
let caminho = URL(fileURLWithPath: argumentos[1])
let maximo = argumentos.count > 2 ? (Int(argumentos[2]) ?? 5) : 5

/// Passa uma imagem pelo reconhecimento e devolve o texto.
func reconhecer(_ cg: CGImage) -> String {
    let pedido = VNRecognizeTextRequest()
    pedido.recognitionLevel = .accurate
    pedido.recognitionLanguages = ["pt-BR", "pt", "en-US"]
    pedido.usesLanguageCorrection = true
    let leitor = VNImageRequestHandler(cgImage: cg, options: [:])
    do {
        try leitor.perform([pedido])
    } catch {
        return ""
    }
    var saida = ""
    for observacao in (pedido.results ?? []) {
        if let melhor = observacao.topCandidates(1).first {
            saida += melhor.string + "\n"
        }
    }
    return saida
}

// Foto solta: não passa por PDFKit, vai direto para o reconhecimento.
guard let documento = PDFDocument(url: caminho) else {
    if let imagem = NSImage(contentsOf: caminho),
       let cg = imagem.cgImage(forProposedRect: nil, context: nil, hints: nil) {
        print(reconhecer(cg))
        exit(0)
    }
    FileHandle.standardError.write("não consegui abrir o arquivo\n".data(using: .utf8)!)
    exit(2)
}

// 2x é o suficiente para carimbo e letra miúda de CRLV; 3x dobra o tempo sem
// melhorar o que interessa (medido nos documentos dela em 08/09/2026).
let escala: CGFloat = 2.0
var texto = ""

for indice in 0..<min(documento.pageCount, maximo) {
    guard let pagina = documento.page(at: indice) else { continue }
    let area = pagina.bounds(for: .mediaBox)
    let tamanho = CGSize(width: area.width * escala, height: area.height * escala)
    let imagem = pagina.thumbnail(of: tamanho, for: .mediaBox)
    guard let cg = imagem.cgImage(forProposedRect: nil, context: nil, hints: nil) else { continue }

    texto += reconhecer(cg) + "\n"
}

print(texto)
