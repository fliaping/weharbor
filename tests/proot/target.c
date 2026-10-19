#include <stdio.h>
#include <unistd.h>
#include <string.h>
#include <stdlib.h>
#include <sys/prctl.h>
char secret[64] = "WEHARBOR-SECRET-KEY-0123456789";
int main(int argc,char**argv){
  /* WeChat-like: allow any same-uid process (Yama not present here anyway) */
  FILE*f=fopen(argv[1],"w"); fprintf(f,"%d %p\n",getpid(),(void*)secret); fclose(f);
  for(;;) sleep(1);
}
