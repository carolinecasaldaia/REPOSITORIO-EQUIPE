/* Lançador do aplicativo "Cadastrar Clientes no Astrea".
 *
 * Mesma lição do projeto BAIXAR AUTENTIQUE (18/08/2026): o executável de um
 * aplicativo precisa ser um programa compilado, e não um roteiro de shell.
 * Com um script, o macOS atribui a permissão ao /bin/sh e a autorização de
 * Acesso Total ao Disco dada ao aplicativo não vale para nada — e sem ela a
 * automação não enxerga a pasta do Google Drive.
 *
 * Ele só chama ~/.cadastro-astrea/rodar.sh, que continua sendo o lugar de
 * mexer quando a rotina mudar (e que fica FORA do Drive, de propósito).
 */
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <stdio.h>

int main(void) {
    const char *casa = getenv("HOME");
    if (!casa) return 1;
    char roteiro[1024];
    snprintf(roteiro, sizeof(roteiro), "%s/.cadastro-astrea/rodar.sh", casa);
    execl("/bin/sh", "sh", roteiro, (char *)NULL);
    perror("não consegui chamar o roteiro");
    return 1;
}
