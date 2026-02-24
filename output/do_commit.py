import subprocess
import os

os.chdir('/Users/fernandovieira/Documents/anti_corrupt')

msg = "feat: Phase D - historical database with Wikidata, Wikipedia, TSE and Camara\n\nAdds full historical data pipeline.\n"

with open('output/commit_msg.txt', 'w') as f:
    f.write(msg)

results = {}
results['add'] = subprocess.run(['git', 'add', '-A'], capture_output=True, text=True)
results['commit'] = subprocess.run(['git', 'commit', '-F', 'output/commit_msg.txt'], capture_output=True, text=True)
results['push'] = subprocess.run(['git', 'push', 'origin', 'main'], capture_output=True, text=True)
results['log'] = subprocess.run(['git', 'log', '--oneline', '-5'], capture_output=True, text=True)

with open('output/git_result.txt', 'w') as f:
    for k, r in results.items():
        f.write(f"=={k}==\nRC:{r.returncode}\n{r.stdout}\n{r.stderr}\n")
