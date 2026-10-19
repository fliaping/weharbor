#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <unistd.h>
#include <fcntl.h>
#include <sys/uio.h>
#include <sys/ptrace.h>
#include <sys/wait.h>
int main(int argc,char**argv){
  int pid; void*addr; FILE*f=fopen(argv[1],"r"); fscanf(f,"%d %p",&pid,&addr); fclose(f);
  char buf[64]={0}; char link[512]={0}; char p[64];
  struct iovec l={buf,30}, r={addr,30};
  ssize_t n=process_vm_readv(pid,&l,1,&r,1,0);
  printf("process_vm_readv: %s\n", n>0?buf:strerror(errno));
  snprintf(p,64,"/proc/%d/mem",pid); int fd=open(p,O_RDONLY); memset(buf,0,64);
  if(fd>=0 && pread(fd,buf,30,(off_t)addr)>0) printf("/proc/pid/mem: %s\n",buf); else printf("/proc/pid/mem: %s\n",strerror(errno));
  snprintf(p,64,"/proc/%d/exe",pid); n=readlink(p,link,511); printf("exe: %s\n", n>0?link:strerror(errno));
  snprintf(p,64,"/proc/%d/status",pid); f=fopen(p,"r"); char line[256]; while(f&&fgets(line,256,f)) if(!strncmp(line,"TracerPid",9)) printf("target %s",line); if(f)fclose(f);
  f=fopen("/proc/self/status","r"); while(f&&fgets(line,256,f)) if(!strncmp(line,"TracerPid",9)) printf("self %s",line); if(f)fclose(f);
  if(ptrace(PTRACE_ATTACH,pid,0,0)==0){ int st; waitpid(pid,&st,0); errno=0; long w=ptrace(PTRACE_PEEKDATA,pid,addr,0);
    printf("PTRACE_ATTACH ok, PEEKDATA: %.8s (%s)\n",(char*)&w, errno?strerror(errno):"ok"); ptrace(PTRACE_DETACH,pid,0,0);}
  else printf("PTRACE_ATTACH: %s\n",strerror(errno));
  if(ptrace(PTRACE_SEIZE,pid,0,0)==0){ printf("PTRACE_SEIZE ok\n"); ptrace(PTRACE_DETACH,pid,0,0);} else printf("PTRACE_SEIZE: %s\n",strerror(errno));
  return 0;
}
