# Application Claude — Wrapper natif iOS

Setup Capacitor prêt. Ce dossier contient un projet iOS natif qui embarque la PWA `https://rococo-fairy-07c1b2.netlify.app` dans un WebKit fullscreen.

## Ce qui est déjà fait

- Capacitor + iOS platform initialisés
- `MainViewController.swift` : force le WKWebView à s'étendre derrière notch + home indicator (via `additionalSafeAreaInsets` négatif)
- `Info.plist` : `UIStatusBarHidden=true`, `UIRequiresFullScreen=true`
- `capacitor.config.json` : pointe sur la PWA Netlify, `contentInset=always`, scroll disabled
- GitHub Actions workflow `.github/workflows/build-ios.yml` : build `.ipa` unsigned sur macOS-14 runner (gratuit)

## Ce que tu dois faire (une seule fois)

### 1. Push sur GitHub (10 min)

```bash
cd C:\Users\voltaire\Desktop\application-claude-native
git add -A
git commit -m "Initial native wrapper"
```

Puis crée un repo GitHub (via web ou `gh repo create`) et push :
```bash
git remote add origin https://github.com/TON_USER/application-claude-native.git
git push -u origin main
```

### 2. GitHub Actions build automatique

Dès le push, l'action `build-ios.yml` se lance sur un runner macOS-14 gratuit (10 min). Elle produit un `.ipa` **unsigned**.

- Va sur `github.com/TON_USER/application-claude-native/actions`
- Ouvre le dernier run → **Artifacts** → télécharge `ApplicationClaude-unsigned-ipa`

### 3. Sideload sur iPhone via AltStore (30 min, gratuit)

**AltStore** = signature avec ton Apple ID gratuit, refresh auto tous les 7 jours.

**Setup PC (Windows)** :
1. Installe **iTunes** depuis `apple.com/itunes` (nécessaire pour le driver USB iPhone)
2. Installe **AltServer** depuis `altstore.io`
3. Lance AltServer (icône barre système)

**Setup iPhone** :
1. Connecte iPhone au PC en USB
2. Sur AltServer (PC) → click droit icône → **Install AltStore** → sélectionne ton iPhone → entre ton Apple ID
3. Sur iPhone → **Réglages > Général > VPN & gestion de l'appareil** → fais confiance au certificat AltStore

**Sideload le .ipa** :
1. Envoie-toi le `.ipa` sur iPhone (AirDrop / iCloud / mail)
2. Ouvre le fichier → **Ouvrir avec AltStore**
3. AltStore signe avec ton Apple ID → installe

**Refresh** :
- iPhone + PC sur le même WiFi + AltServer PC lancé → refresh automatique tous les 7 jours
- Sinon 1x/semaine manuel : lance AltStore sur iPhone → tap refresh

## Résultat attendu

L'app apparaît sur ton écran d'accueil (icône générique pour l'instant, à custom). Ouverture = webview **100% fullscreen physique**, sans URL bar, sans black bar, avec notch + home indicator overlayés sur la webview.

C'est le même comportement qu'une app native de l'App Store, mais sans passer par Apple.

## Custom icône & splash

Remplace `ios/App/App/Assets.xcassets/AppIcon.appiconset/` par tes icônes 1024x1024 + splash. Push → nouvelle build auto.

## Alternative si tu ne veux pas GitHub

- **Codemagic** (codemagic.io) : 500 min/mois iOS build gratuit, upload projet en zip
- **PWABuilder** (pwabuilder.com) : entre l'URL PWA → génère package iOS téléchargeable
- **Un pote avec Mac** : `xcodebuild archive` dans `ios/App` en 30 sec
