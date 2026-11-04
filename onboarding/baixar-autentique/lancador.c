/* Lançador do aplicativo "Baixar Contratos Assinados".
 *
 * Precisa ser um executável de verdade, e não um roteiro de shell: quando o
 * executável de um aplicativo é um script, o macOS atribui a permissão ao
 * /bin/sh e a autorização dada ao aplicativo não vale para nada. Foi o que
 * segurou a automação em 18/08/2026.
 *
 * Ele não faz nada além de chamar ~/.baixar-autentique/rodar.sh, que continua
 * sendo o lugar de mexer quando a rotina mudar.
 */
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <stdio.h>

int main(void) {
    const char *casa = getenv("HOME");
    if (!casa) return 1;
    char roteiro[1024];
    snprintf(roteiro, sizeof(roteiro), "%s/.baixar-autentique/rodar.sh", casa);
    execl("/bin/sh", "sh", roteiro, (char *)NULL);
    perror("não consegui chamar o roteiro");
    return 1;
}
