from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from pathlib import Path
import fitz
import os
import json
import requests
import time
import re

OPENROUTER_API_KEY = "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"
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL_NAME = "deepseek/deepseek-chat"

TEXTO_BASE = None

def carregar_base_conhecimento():
    """Load and cache the knowledge base from PDF files"""
    global TEXTO_BASE
    if TEXTO_BASE is None:
        BASE_DIR = Path(__file__).resolve().parent.parent
        pasta_pdfs = os.path.join(BASE_DIR, "pdfs_familias")
        texto_total = ""
        
        for arquivo in os.listdir(pasta_pdfs):
            if arquivo.endswith(".pdf"):
                try:
                    caminho_pdf = os.path.join(pasta_pdfs, arquivo)
                    with fitz.open(caminho_pdf) as doc:
                        for pagina in doc:
                            texto = pagina.get_text()
                            texto = ' '.join(texto.split()).strip()
                            texto_total += texto + "\n\n"
                except Exception as e:
                    print(f"Erro ao processar {arquivo}: {str(e)}")
                    continue
        TEXTO_BASE = texto_total if texto_total else "Base de conhecimento vazia."
    return TEXTO_BASE

def buscar_contexto(pergunta):
    """Search for relevant context in the knowledge base"""
    texto_base = carregar_base_conhecimento()
    if not texto_base or texto_base == "Base de conhecimento vazia.":
        return "Informações de referência não disponíveis."
    
    pergunta_limpa = pergunta.lower().strip()
    palavras_chave = [p for p in pergunta_limpa.split() if len(p) > 3 and p.isalpha()]
    
    if not palavras_chave:
        return "Nenhuma palavra-chave relevante encontrada na pergunta."
    
    linhas_relevantes = []
    for linha in texto_base.split('\n'):
        linha_limpa = linha.strip()
        if linha_limpa and any(palavra in linha_limpa.lower() for palavra in palavras_chave):
            linhas_relevantes.append(linha_limpa)
            if len(linhas_relevantes) >= 50:
                break
                
    return "\n".join(linhas_relevantes) if linhas_relevantes else "Nenhum contexto específico encontrado."

def limpar_texto_definitivo(texto):
    """Clean text from unwanted spaces and formatting"""
    if not texto:
        return texto
    
    texto = re.sub(r'^[\s\u200B-\u200D\uFEFF]+|[\s\u200B-\u200D\uFEFF]+$', '', texto)
    
    texto = re.sub(r'[ \t]+', ' ', texto)

    linhas = [linha.lstrip() for linha in texto.split('\n')]
    linhas = [linha for linha in linhas if linha.strip()]
    
    return '\n'.join(linhas).strip()

def index(request):
    """Main chat view"""
    if 'current_chat' in request.session:
        chat_id = request.session['current_chat']
        conversa_atual = request.session.get('historico', {}).get(chat_id, [])
        conversa_atual = [{
            'content': limpar_texto_definitivo(msg.get('content', '')),
            'is_user': msg.get('is_user', False)
        } for msg in conversa_atual]
    else:
        conversa_atual = []
    
    historico_chats = list(request.session.get('historico', {}).keys())
    
    return render(request, "chatbot/index.html", {
        'messages': conversa_atual,
        'historico_chats': historico_chats
    })

@csrf_exempt
@require_POST
def send_message(request):
    """Handle user messages and generate responses"""
    try:

        if request.content_type == 'application/json':
            data = json.loads(request.body)
            pergunta = limpar_texto_definitivo(data.get('pergunta', ''))
        else:
            pergunta = limpar_texto_definitivo(request.POST.get('pergunta', ''))
        
        if not pergunta:
            return JsonResponse({'error': 'Por favor, digite uma pergunta válida.'}, status=400)
        
        if 'historico' not in request.session:
            request.session['historico'] = {}
        
        chat_id = request.session.get('current_chat')
        if not chat_id:
            chat_id = f"chat_{int(time.time())}"
            request.session['current_chat'] = chat_id
            request.session['historico'][chat_id] = []
            is_new_chat = True
        else:
            is_new_chat = False
        
        contexto = buscar_contexto(pergunta)
        
        prompt = {
            "model": MODEL_NAME,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Aja como um professor de química experiente que ensina alunos do ensino médio. "
                        "Sua linguagem deve ser didática, clara e com um tom descontraído de sala de aula, mas sem "
                        "infantilizar o conteúdo. Você DEVE seguir esta estrutura ao responder: Explique o conceito "
                        "químico de forma objetiva, acessível e bem fundamentada. Use um exemplo do cotidiano ou uma "
                        "analogia compatível com o nível do ensino médio para tornar o conteúdo mais fácil de visualizar. "
                        "Inclua uma pergunta simples no final da explicação para checar se o aluno compreendeu. Sua missão "
                        "é responder qualquer pergunta que eu fizer sobre a Tabela Periódica ou temas relacionados de "
                        "química (como propriedades dos elementos, ligações químicas, estrutura atômica etc.). Adote um tom "
                        "acolhedor, incentive o raciocínio do aluno, e estimule a curiosidade científica."
                    )
                },
                {
                    "role": "user",
                    "content": f"Pergunta: {pergunta}\nContexto: {contexto}"
                }
            ],
            "temperature": 0.7,
            "max_tokens": 500
        }
        
        try:
            headers = {
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": "http://localhost:8000",
                "X-Title": "BotJunior"
            }
            
            response = requests.post(
                OPENROUTER_API_URL,
                headers=headers,
                json=prompt,
                timeout=30
            )
            
            if response.status_code != 200:
                raise Exception(f"Erro na API: {response.text[:200]}")
            
            data = response.json()
            resposta = limpar_texto_definitivo(data['choices'][0]['message']['content'])
        
        except Exception as api_error:
            resposta = "Erro ao gerar resposta. Tente novamente."
        
        request.session['historico'][chat_id].extend([
            {'content': pergunta, 'is_user': True},
            {'content': resposta, 'is_user': False}
        ])
        request.session.modified = True
        
        return JsonResponse({
            'resposta': resposta,
            'chat_id': chat_id,
            'is_new_chat': is_new_chat
        })
    
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

def new_chat(request):
    """Start a new chat session"""
    request.session['current_chat'] = None
    return redirect('index')

def switch_chat(request, chat_id):
    """Switch to an existing chat"""
    if 'historico' in request.session and chat_id in request.session['historico']:
        request.session['current_chat'] = chat_id
    return redirect('index')

@require_POST
def delete_chat(request, chat_id):
    """Delete a chat session"""
    if 'historico' in request.session and chat_id in request.session['historico']:
        if request.session.get('current_chat') == chat_id:
            request.session['current_chat'] = None
        del request.session['historico'][chat_id]
        return JsonResponse({'status': 'success'})
    return JsonResponse({'status': 'error'}, status=404)

@require_POST
def clear_history(request):
    """Clear all chat history"""
    if 'historico' in request.session:
        request.session['historico'] = {}
        request.session['current_chat'] = None
        return JsonResponse({'status': 'success'})
    return JsonResponse({'status': 'error'}, status=400)